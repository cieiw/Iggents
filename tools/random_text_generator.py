"""Lista configurável usada pela etapa de texto aleatório."""

from __future__ import annotations

import random
import json
from pathlib import Path


def load_random_texts(path: str | Path) -> list[str]:
    file_path = Path(path)
    if not file_path.exists():
        return []
    try:
        raw = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("A lista de textos aleatórios está inválida.") from error
    values = raw.get("textos", []) if isinstance(raw, dict) else raw
    if not isinstance(values, list):
        raise RuntimeError("A lista de textos aleatórios deve conter uma lista de textos.")
    return [str(text).strip() for text in values if str(text).strip()]


def save_random_texts(path: str | Path, texts: list[str]) -> list[str]:
    usable = [text.strip() for text in texts if text.strip()]
    if not usable:
        raise ValueError("Informe pelo menos um texto.")
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(json.dumps({"textos": usable}, ensure_ascii=False, indent=2), encoding="utf-8")
    return usable


def random_text(path: str | Path) -> str:
    texts = load_random_texts(path)
    if not texts:
        raise RuntimeError("A lista de textos aleatórios está vazia. Use Gerenciar textos aleatórios.")
    return random.choice(texts)
