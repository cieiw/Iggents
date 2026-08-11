"""Leitura local de códigos recentes do Instagram no Zoho via IMAP."""

from __future__ import annotations

import email
import html
import imaplib
import json
import re
import time
import threading
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path

try:
    from .zoho_credentials import load
except ImportError:  # execução direta dentro da pasta tools
    from zoho_credentials import load


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
USED_CODES_FILE = DATA_DIR / "codigos_instagram_usados.json"
_history_lock = threading.Lock()
# O e-mail pode chegar antes de o fluxo alcançar a etapa de código. Dois
# minutos eram insuficientes e faziam uma mensagem válida ser ignorada.
CODE_RECOVERY_WINDOW_S = 15 * 60


def _extract_instagram_code(body: str) -> str:
    """Extrai o código que o Instagram pede para digitar no aplicativo.

    O Instagram alterna entre desafios de seis dígitos e e-mails de acesso
    contendo oito dígitos.  Nestes últimos a mensagem pode conter números em
    links de login/reset; por isso o texto próximo de "code in the app" é a
    fonte de verdade e deve ser priorizado.
    """
    text = html.unescape(body or "")
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t\r\n]+", " ", text)

    contextual_patterns = (
        r"(?:or\s+use\s+)?this\s+code\s+in\s+the\s+app\s*:\s*(?:\*\*|\*)?\s*(\d{4,8})(?!\d)",
        r"(?:enter|use)\s+(?:this\s+)?(?:confirmation|security|verification|login|access)\s+code(?:\s+in\s+the\s+app)?\s*:\s*(?:\*\*|\*)?\s*(\d{4,8})(?!\d)",
    )
    for pattern in contextual_patterns:
        matched = re.search(pattern, text, flags=re.IGNORECASE)
        if matched:
            return matched.group(1)

    # Compatibilidade com os e-mails tradicionais de confirmação.  Evita
    # capturar trechos numéricos de URLs quando não há uma frase contextual.
    candidates = re.findall(r"(?<!\d)(\d{4,8})(?!\d)", text)
    if not candidates:
        return ""
    return max(candidates, key=len)


def _text(message: email.message.Message) -> str:
    parts = message.walk() if message.is_multipart() else [message]
    output = [str(message.get("Subject", ""))]
    for part in parts:
        if part.get_content_maintype() == "multipart" or part.get_content_type() not in {"text/plain", "text/html"}:
            continue
        payload = part.get_payload(decode=True)
        if payload:
            output.append(payload.decode(part.get_content_charset() or "utf-8", errors="replace"))
    return "\n".join(output)


def _folders(client: imaplib.IMAP4_SSL) -> list[str]:
    status, listed = client.list()
    if status != "OK":
        raise RuntimeError("Não foi possível listar as pastas do Zoho.")
    excluded = {"rascunho", "modelos", "enviadas", "lixeira", "spam", "snoozed"}
    names = []
    for item in listed or []:
        name = item.decode("utf-8", errors="replace").rsplit('"', 2)[1]
        if name.lower() not in excluded:
            names.append(name)
    return names


def _message_addresses(message: email.message.Message) -> set[str]:
    """Lê o destinatário real, inclusive em caixas catch-all/encaminhadas."""
    fields = ("To", "Cc", "Delivered-To", "X-Original-To", "Envelope-To", "X-Envelope-To")
    values = [str(message.get(field, "")).strip() for field in fields]
    values = [value for value in values if value]
    addresses = {address.strip().casefold() for _name, address in getaddresses(values) if address.strip()}
    # No segundo desafio do Instagram o destinatário pode aparecer somente no
    # HTML do corpo (por exemplo, em um link ``mailto:``), enquanto o cabeçalho
    # To contém a caixa catch-all do Zoho. Incluímos esses endereços para não
    # ignorar o código correto daquele aparelho.
    body = _text(message)
    addresses.update(address.casefold() for address in re.findall(
        r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", body, flags=re.IGNORECASE
    ))
    return addresses


def _recent_codes(client: imaplib.IMAP4_SSL, expected_email: str = "", not_before: float = 0) -> list[tuple[float, str, str]]:
    """Lista códigos recentes do Instagram, do mais novo para o mais antigo."""
    candidates: list[tuple[float, str, str]] = []
    for folder in _folders(client):
        escaped = folder.replace('"', '\\"')
        if client.select(f'"{escaped}"', readonly=True)[0] != "OK":
            continue
        _, data = client.uid("search", None, "ALL")
        for uid in data[0].split()[-30:]:
            _, raw = client.uid("fetch", uid, "(RFC822)")
            message = email.message_from_bytes(raw[0][1])
            subject = str(message.get("Subject", "")).lower()
            sender = str(message.get("From", "")).lower()
            # O Instagram usa mais de um assunto para códigos. O remetente é
            # a identificação confiável; exigir a palavra "code" no assunto
            # fazia o segundo desafio do mesmo fluxo ser ignorado.
            if "instagram" not in sender:
                continue
            if expected_email and expected_email.casefold() not in _message_addresses(message):
                continue
            body = _text(message)
            code = _extract_instagram_code(body)
            if not code:
                continue
            try:
                sent_at = parsedate_to_datetime(message.get("Date", "")).timestamp()
            except (TypeError, ValueError, IndexError):
                sent_at = 0
            if sent_at and sent_at < not_before:
                continue
            message_id = str(message.get("Message-ID", "")).strip()
            message_key = message_id or f"{folder}:{uid.decode('ascii', errors='replace')}"
            candidates.append((sent_at, message_key, code))
    return sorted(candidates, key=lambda candidate: candidate[0], reverse=True)


def _reserve_code(message_key: str, code: str) -> bool:
    """Marca uma mensagem como usada antes de ela ser digitada no aparelho."""
    with _history_lock:
        try:
            history = json.loads(USED_CODES_FILE.read_text(encoding="utf-8")) if USED_CODES_FILE.exists() else {}
        except (OSError, json.JSONDecodeError):
            history = {}
        used = set(history.get("message_keys", []))
        if message_key in used:
            return False
        used.add(message_key)
        history["message_keys"] = list(used)
        history.setdefault("usos", []).append({"mensagem": message_key, "codigo": code, "usado_em": time.time()})
        temporary = USED_CODES_FILE.with_suffix(".tmp")
        temporary.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(USED_CODES_FILE)
        return True


def release_instagram_code(message_key: str) -> None:
    """Libera uma reserva quando o código não conseguiu ser digitado.

    A leitura reserva a mensagem para impedir que dois telefones usem o mesmo
    código. Porém, se ADB falhar depois da leitura, a reserva deve ser
    desfeita para que a própria etapa possa tentar novamente.
    """
    if not message_key:
        return
    with _history_lock:
        try:
            history = json.loads(USED_CODES_FILE.read_text(encoding="utf-8")) if USED_CODES_FILE.exists() else {}
        except (OSError, json.JSONDecodeError):
            return
        used = set(history.get("message_keys", []))
        if message_key not in used:
            return
        used.discard(message_key)
        history["message_keys"] = list(used)
        history["usos"] = [
            item for item in history.get("usos", [])
            if str(item.get("mensagem", "")) != message_key
        ]
        try:
            temporary = USED_CODES_FILE.with_suffix(".tmp")
            temporary.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(USED_CODES_FILE)
        except OSError:
            pass


def wait_for_instagram_code(timeout_s: int = 120, cancel_event=None, expected_email: str = "",
                            return_message_key: bool = False) -> str | tuple[str, str]:
    """Aguarda um código recente do Instagram para o e-mail esperado."""
    config = load()
    if not config:
        raise RuntimeError("Configure o Zoho uma vez antes de usar a etapa Obter código.")
    client = imaplib.IMAP4_SSL(config["host"], 993)
    try:
        client.login(config["email"], config["password"])
        end_at = time.monotonic() + max(10, timeout_s)
        # Aceita a mensagem que chegou antes da etapa: o fluxo pode demorar
        # para alcançar o campo de código. Continua filtrando pelo e-mail da
        # identidade e por mensagens ainda não reservadas.
        not_before = time.time() - max(CODE_RECOVERY_WINDOW_S, int(timeout_s) + 120)
        while time.monotonic() < end_at:
            if cancel_event and cancel_event.is_set():
                raise RuntimeError("Busca de código interrompida.")
            for _sent_at, message_key, code in _recent_codes(client, expected_email, not_before):
                if _reserve_code(message_key, code):
                    return (code, message_key) if return_message_key else code
            time.sleep(3)
        raise RuntimeError("Nenhum código recente do Instagram foi encontrado.")
    finally:
        try:
            client.logout()
        except Exception:
            pass
