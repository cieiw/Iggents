"""Lista local de títulos usados pela etapa de título do link."""

from __future__ import annotations

import random
from pathlib import Path


def load_link_titles(path: str | Path) -> list[str]:
    file_path = Path(path)
    if not file_path.exists():
        return []
    return [line.strip() for line in file_path.read_text(encoding="utf-8").splitlines() if line.strip()]


def save_link_titles(path: str | Path, titles: list[str]) -> list[str]:
    usable = [title.strip() for title in titles if title.strip()]
    if not usable:
        raise ValueError("Informe pelo menos um título.")
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text("\n".join(usable) + "\n", encoding="utf-8")
    return usable


def random_link_title(path: str | Path) -> str:
    titles = load_link_titles(path)
    if not titles:
        raise RuntimeError("A lista de títulos de links está vazia. Use Gerenciar títulos de links.")
    return random.choice(titles)
