"""Transcrição Whisper e extração de códigos de verificação."""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
import threading
from pathlib import Path

_MODEL_CACHE: dict[tuple[str, str], object] = {}
_MODEL_LOCK = threading.RLock()
_TRANSCRIBE_LOCK = threading.RLock()

_DIGITS = {
    "zero": "0", "oh": "0", "o": "0",
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9",
}
_NATO = {
    "alpha": "A", "bravo": "B", "charlie": "C", "delta": "D", "echo": "E",
    "foxtrot": "F", "golf": "G", "hotel": "H", "india": "I", "juliet": "J",
    "juliett": "J", "kilo": "K", "lima": "L", "mike": "M", "november": "N",
    "oscar": "O", "papa": "P", "quebec": "Q", "romeo": "R", "sierra": "S",
    "tango": "T", "uniform": "U", "victor": "V", "whiskey": "W", "xray": "X",
    "x-ray": "X", "yankee": "Y", "zulu": "Z",
}
_CODE_CONTEXT = re.compile(r"\b(?:verification|security|confirmation|login|access)?\s*code\b", re.I)


def _transcribe_faster_whisper(audio_path: Path, model_name: str) -> str:
    from faster_whisper import WhisperModel  # type: ignore

    key = ("faster-whisper", model_name)
    with _MODEL_LOCK:
        model = _MODEL_CACHE.get(key)
        if model is None:
            device = os.environ.get("IGGEN_WHISPER_DEVICE", "cpu")
            compute_type = os.environ.get("IGGEN_WHISPER_COMPUTE_TYPE", "int8" if device == "cpu" else "float16")
            model = WhisperModel(model_name, device=device, compute_type=compute_type)
            _MODEL_CACHE[key] = model
    with _TRANSCRIBE_LOCK:
        segments, _info = model.transcribe(str(audio_path), language="en", beam_size=5, vad_filter=True)
        return " ".join(segment.text.strip() for segment in segments if segment.text.strip()).strip()


def _transcribe_openai_whisper(audio_path: Path, model_name: str) -> str:
    import whisper  # type: ignore

    key = ("openai-whisper", model_name)
    with _MODEL_LOCK:
        model = _MODEL_CACHE.get(key)
        if model is None:
            model = whisper.load_model(model_name)
            _MODEL_CACHE[key] = model
    with _TRANSCRIBE_LOCK:
        result = model.transcribe(str(audio_path), language="en", task="transcribe", fp16=False)
    return str(result.get("text", "")).strip()


def _transcribe_cli(audio_path: Path, model_name: str) -> str:
    executable = shutil.which("whisper") or shutil.which("whisper.exe")
    if not executable:
        raise RuntimeError("O executável whisper não foi encontrado no PATH.")
    output_dir = audio_path.parent
    command = [
        executable, str(audio_path), "--model", model_name, "--language", "en",
        "--task", "transcribe", "--output_format", "txt", "--output_dir", str(output_dir),
    ]
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    run = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=900, creationflags=creationflags,
    )
    if run.returncode:
        raise RuntimeError((run.stderr or run.stdout or "Whisper CLI falhou").strip())
    txt_path = output_dir / f"{audio_path.stem}.txt"
    if not txt_path.exists():
        raise RuntimeError("O Whisper CLI não gerou o arquivo de transcrição.")
    return txt_path.read_text(encoding="utf-8", errors="replace").strip()


def transcribe_audio(audio_path: str | Path, model_name: str = "small.en") -> str:
    """Transcreve usando faster-whisper, openai-whisper ou Whisper CLI."""
    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise RuntimeError(f"Áudio não encontrado: {audio_path}")
    model_name = (model_name or "small.en").strip()
    if model_name not in {"small.en", "medium.en"}:
        raise ValueError("Modelo Whisper inválido. Use small.en ou medium.en.")

    errors: list[str] = []
    if importlib.util.find_spec("faster_whisper") is not None:
        try:
            text = _transcribe_faster_whisper(audio_path, model_name)
            if text:
                return text
        except Exception as error:  # fallback intencional para outra implementação
            errors.append(f"faster-whisper: {error}")
    if importlib.util.find_spec("whisper") is not None:
        try:
            text = _transcribe_openai_whisper(audio_path, model_name)
            if text:
                return text
        except Exception as error:
            errors.append(f"openai-whisper: {error}")
    try:
        text = _transcribe_cli(audio_path, model_name)
        if text:
            return text
    except Exception as error:
        errors.append(f"Whisper CLI: {error}")

    detail = " | ".join(errors) if errors else "nenhuma implementação foi localizada"
    raise RuntimeError(
        "Whisper não está disponível. Instale 'faster-whisper' (recomendado) ou 'openai-whisper'. "
        f"Detalhes: {detail}"
    )


def _token_value(token: str) -> str | None:
    clean = token.strip(".,:;!?()[]{}\"'").lower()
    if not clean:
        return None
    if clean in _DIGITS:
        return _DIGITS[clean]
    if clean in _NATO:
        return _NATO[clean]
    if len(clean) == 1 and clean.isalpha():
        return clean.upper()
    if clean.isdigit() and len(clean) <= 10:
        return clean
    if re.fullmatch(r"[a-z0-9]{4,10}", clean, re.I) and any(char.isdigit() for char in clean):
        return clean.upper()
    return None


def _candidate_from_fragment(fragment: str) -> str | None:
    direct = re.search(r"\b(?=[A-Z0-9]{4,10}\b)(?=[A-Z0-9]*\d)[A-Z0-9]+\b", fragment.upper())
    if direct:
        return direct.group(0)

    pieces: list[str] = []
    for token in re.findall(r"[A-Za-z]+(?:-[A-Za-z]+)?|\d+", fragment):
        value = _token_value(token)
        if value is None:
            if pieces:
                break
            continue
        pieces.append(value)
        candidate = "".join(pieces)
        if len(candidate) >= 4 and len(candidate) <= 10 and any(char.isdigit() for char in candidate):
            # Continua lendo tokens unitários para não truncar A7B92K em A7B9.
            continue
        if len(candidate) > 10:
            break
    candidate = "".join(pieces)
    if 4 <= len(candidate) <= 10 and candidate.isalnum() and any(char.isdigit() for char in candidate):
        return candidate.upper()
    return None


def extract_verification_code(transcript: str) -> str:
    """Extrai códigos numéricos ou alfanuméricos de 4 a 10 caracteres."""
    text = " ".join((transcript or "").split())
    if not text:
        raise RuntimeError("O Whisper não reconheceu nenhuma fala no áudio.")

    contexts = list(_CODE_CONTEXT.finditer(text))
    for match in reversed(contexts):
        candidate = _candidate_from_fragment(text[match.end(): match.end() + 100])
        if candidate:
            return candidate

    candidates = re.findall(r"\b(?=[A-Za-z0-9]{4,10}\b)(?=[A-Za-z0-9]*\d)[A-Za-z0-9]+\b", text)
    if candidates:
        return candidates[-1].upper()

    candidate = _candidate_from_fragment(text)
    if candidate:
        return candidate
    raise RuntimeError(f"Não foi possível extrair um código da transcrição: {text[:180]}")
