"""Gera e reserva endereços únicos a partir das listas do IGGen."""

from __future__ import annotations

import json
import random
import re
import threading
import unicodedata
from datetime import datetime, timezone
from pathlib import Path


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
LISTS_DIR = DATA_DIR / "listas_nomes"
NAMES_FILE = LISTS_DIR / "nomes.txt"
NAMES_DATA_FILE = LISTS_DIR / "nomes.json"
RANDOM_USERS_FILE = LISTS_DIR / "usuarioAleatorioTreino.txt"
RANDOM_USERS_DATA_FILE = LISTS_DIR / "usuarioAleatorioTreino.json"
HISTORY_FILE = DATA_DIR / "emails_usados.json"
# Arquivo de leitura rápida, deixado na raiz do projeto para a pessoa localizar
# sem precisar abrir o JSON técnico dentro da pasta data.
IDENTITIES_REPORT_FILE = DATA_DIR.parent / "USUARIOS_JA_USADOS.txt"
_lock = threading.Lock()
PASSWORD_FORMULA = (
    "inicial do nome + inicial do sobrenome + "
    "3 primeiras letras do sobrenome invertidas (duas vezes) + "
    "quantidade de letras do nome"
)


def _read_list(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_name_profiles() -> list[dict[str, object]]:
    """Lê os nomes que geram e-mails e seus vínculos futuros."""
    if NAMES_DATA_FILE.exists():
        raw = json.loads(NAMES_DATA_FILE.read_text(encoding="utf-8"))
        values = raw.get("nomes", []) if isinstance(raw, dict) else raw
    else:
        values = _read_list(NAMES_FILE)
        NAMES_DATA_FILE.write_text(json.dumps({"nomes": values}, ensure_ascii=False, indent=2), encoding="utf-8")
    profiles = [profile for value in values if (profile := _normalize_random_user(value))]
    if not profiles:
        raise RuntimeError("A lista de nomes deve conter ao menos um nome.")
    return profiles


def save_name_profiles(profiles: list[dict[str, object]]) -> None:
    normalized = [profile for value in profiles if (profile := _normalize_random_user(value))]
    if not normalized:
        raise RuntimeError("Mantenha ao menos um nome na lista.")
    # Preserva os personagens cadastrados no mesmo arquivo. Antes esta função
    # regravava somente ``nomes`` e apagava silenciosamente os novos vínculos.
    existing: dict[str, object] = {}
    if NAMES_DATA_FILE.exists():
        try:
            raw = json.loads(NAMES_DATA_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                existing = raw
        except (OSError, json.JSONDecodeError):
            pass
    existing["nomes"] = normalized
    existing.setdefault("personagens", [])
    NAMES_DATA_FILE.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")


def random_name_profile() -> dict[str, object]:
    return random.choice(load_name_profiles())


def _normalize_character(value: object) -> dict[str, object] | None:
    """Normaliza um personagem e sua pasta-base de mídias."""
    if not isinstance(value, dict):
        return None
    name = str(value.get("nome", "")).strip()
    folder = str(value.get("pasta", "")).strip()
    if not name or not folder:
        return None
    links = value.get("links", [])
    if isinstance(links, str):
        links = links.splitlines()
    if not isinstance(links, list):
        raise RuntimeError(f"Os links do personagem {name} devem formar uma lista.")
    normalized_links = [str(link).strip() for link in links if str(link).strip()]
    return {"nome": name, "pasta": folder, "links": normalized_links}


def load_random_characters() -> list[dict[str, object]]:
    """Lê os personagens que podem ser vinculados a uma identidade."""
    if not NAMES_DATA_FILE.exists():
        return []
    try:
        raw = json.loads(NAMES_DATA_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("O arquivo nomes.json está inválido.") from exc
    values = raw.get("personagens", []) if isinstance(raw, dict) else []
    if not isinstance(values, list):
        raise RuntimeError("A lista de personagens em nomes.json deve ser uma lista.")
    return [character for value in values if (character := _normalize_character(value))]


def save_random_characters(characters: list[dict[str, object]]) -> None:
    """Salva personagens sem alterar a lista de nomes aleatórios."""
    normalized = [character for value in characters if (character := _normalize_character(value))]
    existing: dict[str, object] = {}
    if NAMES_DATA_FILE.exists():
        try:
            raw = json.loads(NAMES_DATA_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                existing = raw
        except (OSError, json.JSONDecodeError):
            pass
    existing.setdefault("nomes", [])
    existing["personagens"] = normalized
    NAMES_DATA_FILE.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")


def random_character_profile(exclude_name: str = "") -> dict[str, object] | None:
    """Sorteia um personagem, podendo excluir o vínculo anterior."""
    characters = load_random_characters()
    if not characters:
        return None
    excluded = exclude_name.strip().casefold()
    candidates = [character for character in characters
                  if str(character.get("nome", "")).strip().casefold() != excluded]
    if excluded and not candidates:
        raise RuntimeError("Cadastre ao menos dois personagens para gerar uma nova identidade com personagem diferente.")
    return random.choice(candidates or characters)


def _normalize_random_user(value: object) -> dict[str, object] | None:
    if isinstance(value, str):
        name = value.strip()
        return {"nome": name, "link": "", "links": [], "arquivos": []} if name else None
    if not isinstance(value, dict):
        return None
    name = str(value.get("nome", "")).strip()
    if not name:
        return None
    files = value.get("arquivos", [])
    if not isinstance(files, list):
        raise RuntimeError(f"Os arquivos de {name} devem formar uma lista.")
    links = value.get("links", [])
    if isinstance(links, str):
        links = links.splitlines()
    if not isinstance(links, list):
        raise RuntimeError(f"Os links de {name} devem formar uma lista.")
    normalized_links = [str(link).strip() for link in links if str(link).strip()]
    legacy_link = str(value.get("link", "")).strip()
    if legacy_link and legacy_link not in normalized_links:
        normalized_links.insert(0, legacy_link)
    return {
        "nome": name,
        # `link` permanece como compatibilidade para fluxos e arquivos
        # antigos; novas execuções usam `links` e sorteiam um item.
        "link": normalized_links[0] if normalized_links else "",
        "links": normalized_links,
        "arquivos": [str(path).strip() for path in files if str(path).strip()],
    }


def load_random_users() -> list[dict[str, object]]:
    """Lê a base de usuários e migra automaticamente a antiga lista de texto."""
    if RANDOM_USERS_DATA_FILE.exists():
        try:
            raw = json.loads(RANDOM_USERS_DATA_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("O arquivo usuariosAleatorios.json está inválido.") from exc
        values = raw.get("nomes", raw.get("usuarios", [])) if isinstance(raw, dict) else raw
        if not isinstance(values, list):
            raise RuntimeError("usuariosAleatorios.json deve conter uma lista de usuários.")
    else:
        values = _read_list(RANDOM_USERS_FILE)
        migrated = [user for value in values if (user := _normalize_random_user(value))]
        RANDOM_USERS_DATA_FILE.write_text(
        json.dumps({"nomes": migrated}, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        values = migrated
    users = [user for value in values if (user := _normalize_random_user(value))]
    if not users:
        raise RuntimeError("A lista usuariosAleatorios deve conter ao menos um usuário com nome.")
    return users


def save_random_users(users: list[dict[str, object]]) -> None:
    """Salva usuários normalizados para edição pela interface."""
    normalized = [user for value in users if (user := _normalize_random_user(value))]
    if not normalized:
        raise RuntimeError("Mantenha ao menos um usuário com nome na lista.")
    RANDOM_USERS_DATA_FILE.write_text(
        json.dumps({"nomes": normalized}, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def random_user() -> dict[str, object]:
    """Sorteia um usuário com nome, link e arquivos para as próximas etapas."""
    return random.choice(load_random_users())


def random_training_username() -> str:
    """Sorteia um usuário da lista pequena usada no treinamento."""
    return str(random_user()["nome"])


def next_training_username(remaining: object = None) -> tuple[str, list[str]]:
    """Entrega cada usuário de treino uma vez antes de montar nova rodada."""
    available = [str(user["nome"]).strip() for user in load_random_users() if str(user.get("nome", "")).strip()]
    if not available:
        raise RuntimeError("A lista de usuários de treino está vazia.")
    valid_remaining = [str(value).strip() for value in (remaining if isinstance(remaining, list) else [])
                       if str(value).strip() in available]
    if not valid_remaining:
        valid_remaining = list(available)
        random.shuffle(valid_remaining)
    username = valid_remaining.pop(0)
    return username, valid_remaining


def random_first_name() -> str:
    """Compatibilidade para a etapa atual, que ainda precisa somente do nome."""
    return str(random_user()["nome"])


def _email_part(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]", "", without_accents.lower())


def password_for(first_name: str, last_name: str) -> str:
    """Cria a senha somente a partir do nome que originou o e-mail."""
    first = _email_part(first_name)
    last = _email_part(last_name)
    if not first or len(last) < 3:
        raise ValueError("Nome e sobrenome precisam ter letras suficientes para gerar a senha.")
    reversed_prefix = last[:3][::-1]
    return f"{first[0]}{last[0]}{reversed_prefix}{reversed_prefix}{len(first)}"


def _load_history() -> dict:
    if not HISTORY_FILE.exists():
        return {"password_formula": PASSWORD_FORMULA, "used_usernames": [], "reservations": [],
                "used_instagram_usernames": [], "instagram_reservations": []}
    try:
        data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        data.setdefault("used_usernames", [])
        data.setdefault("reservations", [])
        data.setdefault("used_instagram_usernames", [])
        data.setdefault("instagram_reservations", [])
        data["password_formula"] = PASSWORD_FORMULA
        for reservation in data["reservations"]:
            if "senha" not in reservation and reservation.get("nome") and reservation.get("sobrenome"):
                reservation["senha"] = password_for(reservation["nome"], reservation["sobrenome"])
        # Migra as identidades antigas: se elas vierem a passar pela etapa de
        # criar @, já contam como reservadas e nunca serão reaproveitadas.
        if not data["instagram_reservations"]:
            seen_instagram: set[str] = set()
            for reservation in data["reservations"]:
                try:
                    username = instagram_username_for(str(reservation.get("nome", "")), str(reservation.get("sobrenome", "")))
                except ValueError:
                    continue
                if username in seen_instagram:
                    continue
                seen_instagram.add(username)
                data["instagram_reservations"].append({
                    "usuario": username, "nome": reservation.get("nome", ""),
                    "sobrenome": reservation.get("sobrenome", ""), "celular": reservation.get("celular"),
                    "reservado_em": reservation.get("reservado_em", ""),
                })
            data["used_instagram_usernames"] = sorted(seen_instagram)
        return data
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("O histórico de e-mails usados está inválido.") from exc


def _save_history(data: dict) -> None:
    temporary = HISTORY_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(HISTORY_FILE)
    _save_identities_report(data)


def _save_identities_report(history: dict) -> None:
    """Gera uma lista direta de todas as identidades, sem alterar o histórico."""
    email_by_name = {
        (_email_part(str(item.get("nome", ""))), _email_part(str(item.get("sobrenome", "")))): item
        for item in history.get("reservations", [])
        if isinstance(item, dict)
    }
    instagram_by_name = {
        (_email_part(str(item.get("nome", ""))), _email_part(str(item.get("sobrenome", "")))): item
        for item in history.get("instagram_reservations", [])
        if isinstance(item, dict)
    }
    keys = list(dict.fromkeys([*email_by_name, *instagram_by_name]))
    lines = [
        "IDENTIDADES JÁ USADAS — iggents",
        "Atualizado automaticamente pelo aplicativo.",
        "",
    ]
    if not keys:
        lines.append("Nenhuma identidade foi registrada ainda.")
    else:
        for index, key in enumerate(keys, 1):
            email_data = email_by_name.get(key, {})
            instagram_data = instagram_by_name.get(key, {})
            name = str(email_data.get("nome") or instagram_data.get("nome") or "").strip()
            last_name = str(email_data.get("sobrenome") or instagram_data.get("sobrenome") or "").strip()
            username = str(instagram_data.get("usuario") or "").strip()
            email = str(email_data.get("email") or "").strip()
            password = str(email_data.get("senha") or "").strip()
            serial = str(email_data.get("celular") or instagram_data.get("celular") or "sem celular vinculado").strip()
            created_at = str(email_data.get("reservado_em") or instagram_data.get("reservado_em") or "").strip()
            lines.extend([
                f"{index}. {name} {last_name}".strip(),
                f"   @: @{username}" if username else "   @: —",
                f"   E-mail: {email or '—'}",
                f"   Senha: {password or '—'}",
                f"   Celular: {serial}",
                f"   Registrado em: {created_at or '—'}",
                "",
            ])
    temporary = IDENTITIES_REPORT_FILE.with_suffix(".tmp")
    temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    temporary.replace(IDENTITIES_REPORT_FILE)


def load_used_identities() -> list[dict[str, str]]:
    """Lista as identidades reservadas para o gerenciador do aplicativo."""
    with _lock:
        history = _load_history()
        emails_by_key = {
            (_email_part(str(item.get("nome", ""))), _email_part(str(item.get("sobrenome", "")))): item
            for item in history.get("reservations", []) if isinstance(item, dict)
        }
        instagram_by_key = {
            (_email_part(str(item.get("nome", ""))), _email_part(str(item.get("sobrenome", "")))): item
            for item in history.get("instagram_reservations", []) if isinstance(item, dict)
        }
        keys = list(dict.fromkeys([*emails_by_key, *instagram_by_key]))
        values: list[dict[str, str]] = []
        for first_key, last_key in keys:
            email_item = emails_by_key.get((first_key, last_key), {})
            instagram_item = instagram_by_key.get((first_key, last_key), {})
            values.append({
                "nome": str(email_item.get("nome") or instagram_item.get("nome") or "").strip(),
                "sobrenome": str(email_item.get("sobrenome") or instagram_item.get("sobrenome") or "").strip(),
                "email": str(email_item.get("email") or "").strip(),
                "usuario": str(instagram_item.get("usuario") or "").strip(),
                "celular": str(email_item.get("celular") or instagram_item.get("celular") or "").strip(),
                "reservado_em": str(email_item.get("reservado_em") or instagram_item.get("reservado_em") or "").strip(),
            })
        return values


def release_used_identity(first_name: str, last_name: str) -> bool:
    """Libera uma identidade do histórico para que possa ser criada novamente.

    Isto remove somente a reserva histórica. Os dados que eventualmente já
    estejam vinculados ao telefone continuam intactos no arquivo do aparelho.
    """
    first_key, last_key = _email_part(first_name), _email_part(last_name)
    if not first_key or not last_key:
        raise ValueError("Informe nome e sobrenome da identidade.")
    with _lock:
        history = _load_history()
        def same_identity(item: object) -> bool:
            return isinstance(item, dict) and (
                _email_part(str(item.get("nome", ""))),
                _email_part(str(item.get("sobrenome", ""))),
            ) == (first_key, last_key)

        removed_emails = [item for item in history["reservations"] if same_identity(item)]
        removed_instagram = [item for item in history["instagram_reservations"] if same_identity(item)]
        if not removed_emails and not removed_instagram:
            return False
        history["reservations"] = [item for item in history["reservations"] if not same_identity(item)]
        history["instagram_reservations"] = [item for item in history["instagram_reservations"] if not same_identity(item)]
        history["used_usernames"] = sorted({
            _email_part(str(item.get("nome", ""))) + _email_part(str(item.get("sobrenome", "")))
            for item in history["reservations"] if isinstance(item, dict)
        })
        history["used_instagram_usernames"] = sorted({
            str(item.get("usuario", "")).strip()
            for item in history["instagram_reservations"]
            if isinstance(item, dict) and str(item.get("usuario", "")).strip()
        })
        _save_history(history)
    return True


def reserve_email(domain: str = "hotvinci.online", device_serial: str | None = None,
                  first_name: str | None = None) -> dict[str, str]:
    """Reserva uma combinação inédita e devolve nome, sobrenome e e-mail."""
    domain = domain.strip().lower().lstrip("@")
    if not domain or "." not in domain:
        raise ValueError("Informe um domínio válido, por exemplo hotvinci.online.")

    first_names = [str(profile["nome"]) for profile in load_name_profiles()]
    last_names = _read_list(LISTS_DIR / "sobrenomes.txt")
    if first_name:
        first_names = [first for first in first_names if first == first_name]
        if not first_names:
            raise RuntimeError(f"O nome {first_name} não existe na lista de nomes.")
    choices = [(first, last, _email_part(first) + _email_part(last)) for first in first_names for last in last_names]

    with _lock:
        history = _load_history()
        used = set(history["used_usernames"])
        used_instagram = set(history["used_instagram_usernames"])
        # A identidade reserva também o @ que ela formará depois. Isso evita
        # que um sobrenome novo gere o mesmo @ de uma identidade antiga.
        available = [
            choice for choice in choices
            if choice[2] not in used
            and instagram_username_for(choice[0], choice[1]) not in used_instagram
        ]
        if not available:
            raise RuntimeError(f"Todas as {len(choices)} combinações já foram usadas.")
        first, last, username = random.choice(available)
        address = f"{username}@{domain}"
        password = password_for(first, last)
        history["used_usernames"].append(username)
        history["reservations"].append({
            "email": address,
            "nome": first,
            "sobrenome": last,
            "senha": password,
            "celular": device_serial,
            "reservado_em": datetime.now(timezone.utc).isoformat(),
        })
        instagram_username = instagram_username_for(first, last)
        history["used_instagram_usernames"].append(instagram_username)
        history["instagram_reservations"].append({
            "usuario": instagram_username,
            "nome": first,
            "sobrenome": last,
            "celular": device_serial,
            "reservado_em": history["reservations"][-1]["reservado_em"],
        })
        _save_history(history)
    return {"nome": first, "sobrenome": last, "email": address, "senha": password}


def reserve_named_email(first_name: str, last_name: str, domain: str = "hotvinci.online",
                        device_serial: str | None = None) -> dict[str, str]:
    """Reserva uma combinação informada manualmente, sem permitir repetição."""
    first, last = first_name.strip(), last_name.strip()
    domain = domain.strip().lower().lstrip("@")
    if not first or not last or not domain or "." not in domain:
        raise ValueError("Informe nome, sobrenome e domínio válidos.")
    username = _email_part(first) + _email_part(last)
    address, password = f"{username}@{domain}", password_for(first, last)
    with _lock:
        history = _load_history()
        for item in history["reservations"]:
            if _email_part(str(item.get("nome", ""))) + _email_part(str(item.get("sobrenome", ""))) != username:
                continue
            if device_serial and item.get("celular") == device_serial:
                return {"nome": first, "sobrenome": last, "email": address, "senha": password}
            raise RuntimeError(f"A combinação {first} {last} já está reservada para outro celular.")
        if username in history["used_usernames"]:
            raise RuntimeError(f"A combinação {first} {last} já foi usada e não pode ser repetida.")
        instagram_username = instagram_username_for(first, last)
        if instagram_username in history["used_instagram_usernames"]:
            raise RuntimeError(f"O usuário @{instagram_username} já foi reservado por outra combinação.")
        history["used_usernames"].append(username)
        history["reservations"].append({"email": address, "nome": first, "sobrenome": last,
                                        "senha": password, "celular": device_serial,
                                        "reservado_em": datetime.now(timezone.utc).isoformat()})
        history["used_instagram_usernames"].append(instagram_username)
        history["instagram_reservations"].append({
            "usuario": instagram_username, "nome": first, "sobrenome": last,
            "celular": device_serial, "reservado_em": history["reservations"][-1]["reservado_em"],
        })
        _save_history(history)
    return {"nome": first, "sobrenome": last, "email": address, "senha": password}


def instagram_username_for(first_name: str, last_name: str) -> str:
    """Aplica a fórmula usada pela etapa «Nome de usuário» do iggen."""
    first, last = _email_part(first_name), _email_part(last_name)
    if not first or len(last) < 3:
        raise ValueError("Nome e sobrenome precisam ter ao menos três letras para gerar o usuário.")
    return f"{last[:3]}{last[2:3] * 2}{first}sz"


def reserve_instagram_username(first_name: str, last_name: str, device_serial: str | None = None) -> str:
    """Reserva o @ final, impedindo repetição mesmo com prefixos iguais.

    Reexecutar a etapa no mesmo celular devolve o mesmo @; outro celular não
    pode reutilizá-lo. O histórico fica junto das identidades já reservadas.
    """
    username = instagram_username_for(first_name, last_name)
    with _lock:
        history = _load_history()
        for item in history["instagram_reservations"]:
            if str(item.get("usuario", "")) != username:
                continue
            if device_serial and item.get("celular") == device_serial:
                return username
            raise RuntimeError(f"O usuário @{username} já foi reservado para outro celular.")
        if username in history["used_instagram_usernames"]:
            raise RuntimeError(f"O usuário @{username} já foi usado e não pode ser repetido.")
        history["used_instagram_usernames"].append(username)
        history["instagram_reservations"].append({
            "usuario": username,
            "nome": first_name.strip(),
            "sobrenome": last_name.strip(),
            "celular": device_serial,
            "reservado_em": datetime.now(timezone.utc).isoformat(),
        })
        _save_history(history)
    return username


def latest_identity_for_device(device_serial: str | None) -> dict[str, str]:
    """Retorna a última identidade criada para este celular.

    O fallback mantém compatibilidade com reservas feitas antes desta associação.
    """
    with _lock:
        history = _load_history()
        reservations = history["reservations"]
        if device_serial:
            for item in reversed(reservations):
                if item.get("celular") == device_serial and item.get("senha"):
                    return item
        for item in reversed(reservations):
            if item.get("senha"):
                return item
    raise RuntimeError("Ainda não existe uma senha gerada no histórico.")


if __name__ == "__main__":
    identity = reserve_email()
    print(f"Nome: {identity['nome']} {identity['sobrenome']}")
    print(f"E-mail reservado: {identity['email']}")
    print(f"Senha: {identity['senha']}")
