"""Captura de áudio do Android via scrcpy e conversão para Whisper."""

from __future__ import annotations

import os
import random
import shutil
import shlex
import socket
import struct
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tools.runtime_variables import runtime_dir_for


@dataclass(frozen=True)
class AudioFiles:
    directory: Path
    m4a: Path
    wav: Path


def _first_existing(candidates: list[Path]) -> Path | None:
    return next((path for path in candidates if path.is_file()), None)


def find_scrcpy(app_dir: str | Path) -> Path:
    app_dir = Path(app_dir)
    candidates = sorted((app_dir / "tools" / "scrcpy").rglob("scrcpy.exe"))
    found = _first_existing(candidates)
    if found:
        return found
    system = shutil.which("scrcpy") or shutil.which("scrcpy.exe")
    if system:
        return Path(system)
    raise RuntimeError("scrcpy não foi encontrado em tools\\scrcpy nem no PATH.")


def find_ffmpeg(app_dir: str | Path) -> Path:
    app_dir = Path(app_dir)
    candidates = [app_dir / "tools" / "ffmpeg" / "ffmpeg.exe", app_dir / "tools" / "ffmpeg.exe", app_dir / "ffmpeg.exe"]
    found = _first_existing(candidates)
    if not found and (app_dir / "tools").exists():
        found = _first_existing(sorted((app_dir / "tools").rglob("ffmpeg.exe")))
    if found:
        return found
    system = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    if system:
        return Path(system)
    raise RuntimeError("FFmpeg não foi encontrado. Instale-o no PATH ou coloque ffmpeg.exe em tools\\ffmpeg\\.")


def _run_process(command: list[str], timeout: float, stop_event: Any = None) -> subprocess.CompletedProcess[str]:
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                               encoding="utf-8", errors="replace", creationflags=creationflags)
    deadline = time.monotonic() + timeout
    while process.poll() is None:
        if stop_event is not None and stop_event.is_set():
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
            raise RuntimeError("Captura de áudio interrompida.")
        if time.monotonic() >= deadline:
            process.kill()
            stdout, stderr = process.communicate()
            raise RuntimeError(f"O processo de áudio excedeu o tempo limite: {(stderr or stdout or 'tempo limite excedido').strip()}")
        time.sleep(.1)
    stdout, stderr = process.communicate()
    if process.returncode:
        raise RuntimeError(f"Falha ao executar {' '.join(command[:2])}: {(stderr or stdout or 'sem detalhes').strip()}")
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


_SCRCPY_AAC_CODEC_ID = b"\x00aac"
_SCRCPY_PACKET_FLAG_SESSION = 1 << 63
_SCRCPY_PACKET_FLAG_CONFIG = 1 << 62


def _has_root_access(adb: Path, serial: str) -> bool:
    try:
        probe = subprocess.run([str(adb), "-s", serial, "shell", "su", "-c", "id"],
                               capture_output=True, text=True, timeout=8)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return probe.returncode == 0 and "uid=0" in probe.stdout


def _adb_su_command(adb: Path, serial: str, command: str) -> list[str]:
    """Monta ``adb shell su -c`` sem deixar o Android quebrar o comando.

    ``adb shell su -c cmd arg`` entrega apenas ``cmd`` ao ``su -c``. O
    servidor Java precisa chegar inteiro como uma única string (inclusive as
    atribuições CLASSPATH), ou app_process é iniciado novamente como shell.
    """
    return [str(adb), "-s", serial, "shell", f"su -c {shlex.quote(command)}"]


def _read_socket_exact(stream: socket.socket, size: int, deadline: float, stop_event: Any) -> bytes:
    """Lê um campo do protocolo, inclusive quando TCP o fragmenta."""
    chunks: list[bytes] = []
    while size:
        if stop_event is not None and stop_event.is_set():
            raise RuntimeError("Captura de áudio interrompida.")
        if time.monotonic() >= deadline:
            raise RuntimeError("O servidor root de áudio parou antes do fim do pacote scrcpy.")
        try:
            data = stream.recv(size)
        except socket.timeout:
            continue
        if not data:
            raise RuntimeError("O servidor root de áudio encerrou a conexão inesperadamente.")
        chunks.append(data)
        size -= len(data)
    return b"".join(chunks)


def _adts_header(config: bytes, payload_size: int) -> bytes:
    """Converte AudioSpecificConfig do MediaCodec em cabeçalho ADTS."""
    if len(config) < 2:
        raise RuntimeError("O scrcpy enviou uma configuração AAC incompleta.")
    raw, total_bits, cursor = int.from_bytes(config, "big"), len(config) * 8, 0

    def take(count: int) -> int:
        nonlocal cursor
        if cursor + count > total_bits:
            raise RuntimeError("Configuração AAC inválida enviada pelo scrcpy.")
        value = (raw >> (total_bits - cursor - count)) & ((1 << count) - 1)
        cursor += count
        return value

    object_type = take(5)
    if object_type == 31:
        object_type = 32 + take(6)
    frequency_index = take(4)
    if frequency_index == 15:
        raise RuntimeError("A configuração AAC usa frequência explícita incompatível com ADTS.")
    channels = take(4)
    if not 1 <= object_type <= 4 or not 0 <= frequency_index <= 12 or not 1 <= channels <= 7:
        raise RuntimeError(f"Configuração AAC incompatível com ADTS (perfil={object_type}, frequência={frequency_index}, canais={channels}).")
    frame_length = payload_size + 7
    if frame_length > 0x1FFF:
        raise RuntimeError("Pacote AAC grande demais para ADTS.")
    return bytes((0xFF, 0xF1, ((object_type - 1) << 6) | (frequency_index << 2) | (channels >> 2),
                  ((channels & 3) << 6) | (frame_length >> 11), (frame_length >> 3) & 0xFF,
                  ((frame_length & 7) << 5) | 0x1F, 0xFC))


def _capture_root_audio_once(serial: str, app_dir: Path, duration_s: int, output: Path, stop_event: Any = None) -> None:
    """Demultiplexa o socket de áudio scrcpy 4.1 iniciado por ``su``."""
    scrcpy = find_scrcpy(app_dir)
    adb = scrcpy.parent / "adb.exe"
    if not adb.exists():
        raise RuntimeError("ADB do scrcpy não foi encontrado para a captura root.")
    scid, port = random.randint(1, 0x7fffffff), random.randint(28000, 28999)
    remote = f"/data/local/tmp/iggents-root-audio-server-{scid:08x}"
    socket_name = f"scrcpy_{scid:08x}"
    server_pid: str | None = None
    stream: socket.socket | None = None
    try:
        _run_process([str(adb), "-s", serial, "push", str(scrcpy.parent / "scrcpy-server"), remote], 20)
        _run_process([str(adb), "-s", serial, "forward", f"tcp:{port}", f"localabstract:{socket_name}"], 10)
        arguments = (f"exec env CLASSPATH={remote} app_process / com.genymobile.scrcpy.Server 4.1 "
                     f"scid={scid:08x} log_level=warn video=false audio=true control=false "
                     # Android 13+ expõe o mixer de reprodução por esta fonte;
                     # REMOTE_SUBMIX ("output") retornou silêncio no A14/Android 15.
                     "audio_codec=aac audio_source=playback tunnel_forward=true "
                     "send_device_meta=false send_dummy_byte=false send_stream_meta=true send_frame_meta=true cleanup=false")
        # Inicie em segundo plano e guarde o PID remoto. Encerrar somente o
        # adb shell não encerra app_process de forma confiável em Android.
        launched = subprocess.run(
            _adb_su_command(adb, serial, f"{arguments} >/dev/null 2>&1 & echo $!"),
            capture_output=True, text=True, timeout=10,
        )
        if launched.returncode:
            raise RuntimeError(f"Não foi possível iniciar o servidor root: {(launched.stderr or launched.stdout).strip()}")
        server_pid = next((line.strip() for line in launched.stdout.splitlines() if line.strip().isdigit()), None)
        if not server_pid:
            raise RuntimeError("O servidor root não retornou o PID remoto.")
        # Em alguns Samsung o socket de forward aceita cedo demais; esperar o
        # encoder evita conectar antes de o servidor terminar a inicialização.
        time.sleep(.7)
        deadline = time.monotonic() + 8
        while stream is None:
            try:
                stream = socket.create_connection(("127.0.0.1", port), timeout=1)
            except OSError:
                if time.monotonic() >= deadline:
                    raise RuntimeError("Servidor root de áudio não abriu a conexão ADB.")
                time.sleep(.15)
        stream.settimeout(.5)
        if _read_socket_exact(stream, 4, deadline, stop_event) != _SCRCPY_AAC_CODEC_ID:
            raise RuntimeError("O scrcpy root não iniciou um fluxo AAC.")
        end, config, frames, packets = time.monotonic() + duration_s, None, bytearray(), 0
        while time.monotonic() < end:
            # Se o cabeçalho chegou antes do limite, conceda tempo curto para
            # terminar o payload TCP sem transformar a última access unit em erro.
            packet_deadline = end + 2
            flags_and_pts, payload_size = struct.unpack(">QI", _read_socket_exact(stream, 12, packet_deadline, stop_event))
            if flags_and_pts & _SCRCPY_PACKET_FLAG_SESSION or payload_size > 2 * 1024 * 1024:
                raise RuntimeError("Pacote de áudio scrcpy inválido.")
            payload = _read_socket_exact(stream, payload_size, packet_deadline, stop_event)
            if flags_and_pts & _SCRCPY_PACKET_FLAG_CONFIG:
                config = payload
            elif config is None:
                raise RuntimeError("O scrcpy enviou AAC antes da configuração do codec.")
            else:
                frames.extend(_adts_header(config, len(payload)))
                frames.extend(payload)
                packets += 1
        if not packets:
            raise RuntimeError("A captura root não recebeu pacotes AAC de áudio.")
        output.write_bytes(frames)
    finally:
        if stream:
            stream.close()
        if server_pid:
            subprocess.run(_adb_su_command(adb, serial, f"kill {server_pid}"), capture_output=True)
        # Alguns builds Android deixam app_process reparented após o shell
        # inicial. O padrão [s]cid evita que pkill mate o próprio comando.
        subprocess.run(_adb_su_command(adb, serial, f"pkill -f '[s]cid={scid:08x}'"), capture_output=True)
        subprocess.run([str(adb), "-s", serial, "forward", "--remove", f"tcp:{port}"], capture_output=True)
        subprocess.run(_adb_su_command(adb, serial, f"rm -f {remote}"), capture_output=True)


def _capture_root_audio(serial: str, app_dir: Path, duration_s: int, output: Path, stop_event: Any = None) -> None:
    """Captura root, repetindo somente a corrida de abertura do socket scrcpy.

    Alguns Samsung aceitam a conexão TCP do ``adb forward`` antes de o
    localabstract existir. A conexão então fecha sem bytes. Recriar servidor e
    forward é seguro; nunca há fallback para a rota sem root aqui.
    """
    error: RuntimeError | None = None
    for attempt in range(3):
        try:
            _capture_root_audio_once(serial, app_dir, duration_s, output, stop_event)
            return
        except RuntimeError as caught:
            error = caught
            if stop_event is not None and stop_event.is_set():
                raise
            if "encerrou a conexão inesperadamente" not in str(caught) or attempt == 2:
                raise
            time.sleep(.4 * (attempt + 1))
    raise error or RuntimeError("Não foi possível iniciar a captura root.")


def capture_device_audio(serial: str, app_dir: str | Path, runtime_root: str | Path, duration_s: int = 10,
                         stop_event: Any = None) -> AudioFiles:
    """Grava a saída do aparelho e cria WAV PCM 16 kHz mono."""
    if not serial:
        raise ValueError("O serial ADB é obrigatório para capturar áudio.")
    duration_s = max(1, min(int(duration_s), 120))
    directory = runtime_dir_for(serial, runtime_root)
    m4a, root_aac, wav = directory / "audio.m4a", directory / "audio-root.aac", directory / "audio.wav"
    for stale in (m4a, root_aac, wav, directory / "transcript.txt"):
        try:
            stale.unlink()
        except FileNotFoundError:
            pass
    scrcpy = find_scrcpy(app_dir)
    adb = scrcpy.parent / "adb.exe"
    root_used = adb.exists() and _has_root_access(adb, serial)
    if root_used:
        # Não há fallback: se root foi detectado, uma falha nesta rota é um erro real.
        _capture_root_audio(serial, Path(app_dir), duration_s, root_aac, stop_event)
    else:
        _run_process([str(scrcpy), "--serial", serial, "--no-video", "--audio-source=output", "--audio-codec=aac",
                      f"--record={m4a}", f"--time-limit={duration_s}"], duration_s + 30, stop_event)
    source = root_aac if root_used else m4a
    if not source.exists() or source.stat().st_size == 0:
        raise RuntimeError("A captura de áudio não gerou arquivo utilizável.")
    _run_process([str(find_ffmpeg(app_dir)), "-y", "-hide_banner", "-loglevel", "error", "-i", str(source),
                  "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(wav)], 60, stop_event)
    if not wav.exists() or wav.stat().st_size == 0:
        raise RuntimeError("O FFmpeg terminou sem gerar audio.wav utilizável.")
    return AudioFiles(directory=directory, m4a=m4a, wav=wav)
