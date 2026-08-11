"""Teste manual de conexão IMAP com o Zoho.

O e-mail e a senha são solicitados no terminal e não são gravados em arquivo.
"""

import argparse
import email
import getpass
import imaplib
import re
import time
from email.utils import parsedate_to_datetime

from zoho_credentials import clear as clear_credentials
from zoho_credentials import load as load_credentials
from zoho_credentials import save as save_credentials


def decode_header_value(value: str | None) -> str:
    """Mostra assunto/remetente de forma legível, inclusive com acentos."""
    if not value:
        return "(sem informação)"
    parts = email.header.decode_header(value)
    return "".join(
        part.decode(charset or "utf-8", errors="replace") if isinstance(part, bytes) else part
        for part, charset in parts
    )


def message_text(message: email.message.Message) -> str:
    """Obtém somente as partes textuais de uma mensagem."""
    parts = message.walk() if message.is_multipart() else [message]
    texts: list[str] = []
    for part in parts:
        if part.get_content_maintype() == "multipart":
            continue
        if part.get_content_type() not in {"text/plain", "text/html"}:
            continue
        payload = part.get_payload(decode=True)
        if not payload:
            continue
        texts.append(payload.decode(part.get_content_charset() or "utf-8", errors="replace"))
    return "\n".join(texts)


def find_codes(message: email.message.Message) -> list[str]:
    """Localiza códigos tanto no assunto quanto no corpo da mensagem."""
    content = f"{decode_header_value(message.get('Subject'))}\n{message_text(message)}"
    return re.findall(r"(?<!\d)(\d{4,8})(?!\d)", content)


def is_instagram_code(message: email.message.Message) -> bool:
    subject = decode_header_value(message.get("Subject")).lower()
    sender = decode_header_value(message.get("From")).lower()
    return "instagram" in subject and "code" in subject and "instagram" in sender


def inbox_folders(client: imaplib.IMAP4_SSL) -> list[str]:
    """Pastas de recebimento que devem ser verificadas para códigos."""
    status, folders = client.list()
    if status != "OK":
        raise RuntimeError("Não foi possível listar as pastas do e-mail.")
    excluded = {"rascunho", "modelos", "enviadas", "lixeira", "spam", "snoozed"}
    names: list[str] = []
    for folder in folders or []:
        text = folder.decode("utf-8", errors="replace")
        name = text.rsplit('"', 2)[1]
        if name.lower() not in excluded:
            names.append(name)
    return names


def select_folder(client: imaplib.IMAP4_SSL, folder: str) -> bool:
    escaped = folder.replace('"', '\\"')
    status, _ = client.select(f'"{escaped}"', readonly=True)
    return status == "OK"


def wait_for_new_code(client: imaplib.IMAP4_SSL, seconds: int) -> None:
    """Aguarda uma mensagem que chegue após o começo do teste."""
    _, initial_data = client.search(None, "ALL")
    known_ids = set(initial_data[0].split())
    print(f"\nAguardando uma mensagem nova por até {seconds} segundos...")
    print("Envie agora um e-mail de teste com, por exemplo, 'Código: 123456'.")

    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        time.sleep(3)
        _, data = client.search(None, "ALL")
        new_ids = [item for item in data[0].split() if item not in known_ids]
        for message_id in new_ids:
            _, raw = client.fetch(message_id, "(RFC822)")
            message = email.message_from_bytes(raw[0][1])
            codes = find_codes(message)
            if codes:
                print(f"\nCódigo encontrado: {codes[0]}")
                return
            known_ids.add(message_id)
    print("\nNenhum código foi encontrado dentro do tempo de espera.")


def show_latest_code(client: imaplib.IMAP4_SSL, instagram_only: bool) -> None:
    """Procura um código nas mensagens já existentes, começando pelas mais novas."""
    _, data = client.search(None, "ALL")
    for message_id in reversed(data[0].split()[-20:]):
        _, raw = client.fetch(message_id, "(RFC822)")
        message = email.message_from_bytes(raw[0][1])
        if instagram_only and not is_instagram_code(message):
            continue
        codes = find_codes(message)
        if codes:
            print(f"\nCódigo mais recente encontrado: {codes[0]}")
            return
    if instagram_only:
        print("\nNenhum e-mail de código do Instagram foi encontrado na INBOX.")
    else:
        print("\nNenhum código de 4 a 8 dígitos foi encontrado na INBOX.")


def show_latest_instagram_code_all_folders(client: imaplib.IMAP4_SSL) -> None:
    """Procura o código mais recente do Instagram nas pastas de recebimento."""
    matches: list[tuple[float, str, str]] = []
    for folder in inbox_folders(client):
        if not select_folder(client, folder):
            continue
        _, data = client.search(None, "ALL")
        for message_id in data[0].split()[-30:]:
            _, raw = client.fetch(message_id, "(RFC822)")
            message = email.message_from_bytes(raw[0][1])
            if not is_instagram_code(message):
                continue
            codes = find_codes(message)
            if not codes:
                continue
            try:
                timestamp = parsedate_to_datetime(message.get("Date", "")).timestamp()
            except (TypeError, ValueError, IndexError):
                timestamp = 0
            matches.append((timestamp, folder, codes[0]))
    if matches:
        _, folder, code = max(matches)
        print(f"\nCódigo do Instagram encontrado em {folder}: {code}")
    else:
        print("\nNenhum e-mail de código do Instagram foi encontrado nas pastas de recebimento.")


def list_folders(client: imaplib.IMAP4_SSL) -> None:
    """Mostra as pastas que o Zoho disponibiliza via IMAP."""
    status, folders = client.list()
    if status != "OK":
        raise RuntimeError("Não foi possível listar as pastas do e-mail.")
    print("\nPastas disponíveis no Zoho:")
    for folder in folders or []:
        print("- " + folder.decode("utf-8", errors="replace"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Teste de IMAP do Zoho Mail")
    parser.add_argument("--wait-code", action="store_true", help="aguarda e extrai um código de e-mail novo")
    parser.add_argument("--latest-code", action="store_true", help="extrai o código mais recente já recebido")
    parser.add_argument("--instagram-code", action="store_true", help="extrai somente o código mais recente do Instagram")
    parser.add_argument("--folders", action="store_true", help="lista as pastas disponíveis no Zoho")
    parser.add_argument("--setup", action="store_true", help="salva uma vez os dados no Windows Credential Manager")
    parser.add_argument("--clear-setup", action="store_true", help="apaga a configuração salva")
    parser.add_argument("--seconds", type=int, default=120, help="tempo máximo de espera (padrão: 120)")
    args = parser.parse_args()

    if args.clear_setup:
        clear_credentials()
        print("Configuração do Zoho removida do Windows.")
        return

    print("Teste de conexão com o Zoho Mail via IMAP\n")
    saved = load_credentials() if not args.setup else None
    if saved:
        address = saved["email"]
        password = saved["password"]
        host = saved["host"]
        print(f"Usando a configuração salva para {address}.\n")
    else:
        address = input("E-mail catch-all: ").strip()
        password = getpass.getpass("Senha de aplicativo do Zoho (não será exibida): ")
        host = input("Servidor [imappro.zoho.com]: ").strip() or "imappro.zoho.com"

    try:
        client = imaplib.IMAP4_SSL(host, 993)
        client.login(address, password)
        status, _ = client.select("INBOX", readonly=True)
        if status != "OK":
            raise RuntimeError("Não foi possível abrir a caixa de entrada.")

        _, data = client.search(None, "ALL")
        ids = data[0].split()
        print(f"\nConectado. Total de mensagens na caixa de entrada: {len(ids)}\n")

        if args.folders:
            list_folders(client)
        elif args.wait_code:
            wait_for_new_code(client, max(args.seconds, 10))
        elif args.instagram_code:
            show_latest_instagram_code_all_folders(client)
        elif args.latest_code:
            show_latest_code(client, instagram_only=False)
        else:
            for message_id in reversed(ids[-5:]):
                _, raw = client.fetch(message_id, "(RFC822.HEADER)")
                message = email.message_from_bytes(raw[0][1])
                print(f"De: {decode_header_value(message.get('From'))}")
                print(f"Assunto: {decode_header_value(message.get('Subject'))}")
                print(f"Data: {message.get('Date', '(sem data)')}")
                print("-" * 48)

        client.logout()
        if args.setup:
            save_credentials(address, password, host)
            print("Configuração salva no Gerenciador de Credenciais do Windows.")
        print("Teste concluído com sucesso.")
    except imaplib.IMAP4.error as exc:
        print(f"\nFalha de autenticação/IMAP: {exc}")
        print("Confira se o IMAP está ativo e se você usou uma senha de aplicativo.")
    except OSError as exc:
        print(f"\nNão foi possível conectar ao servidor: {exc}")
    except Exception as exc:
        print(f"\nErro no teste: {exc}")


if __name__ == "__main__":
    main()
