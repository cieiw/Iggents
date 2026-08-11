"""Variáveis persistentes isoladas por dispositivo ADB.

Cada serial recebe uma pasta própria em ``runtime/<serial>/``. As gravações,
transcrições e variáveis de uma thread nunca são compartilhadas com outro
telefone.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from pathlib import Path
from typing import Any

_LOCKS_GUARD = threading.Lock()
_DEVICE_LOCKS: dict[str, threading.RLock] = {}


def safe_serial_name(serial: str) -> str:
    """Converte um serial ADB em nome de pasta seguro e estável no Windows."""
    serial = (serial or "unknown_device").strip()
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", serial).strip(" ._") or "unknown_device"
    if safe != serial:
        digest = hashlib.sha1(serial.encode("utf-8", "replace")).hexdigest()[:8]
        safe = f"{safe}_{digest}"
    return safe[:120]


def runtime_dir_for(serial: str, root: str | Path) -> Path:
    path = Path(root) / safe_serial_name(serial)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _lock_for(path: Path) -> threading.RLock:
    key = str(path.resolve())
    with _LOCKS_GUARD:
        return _DEVICE_LOCKS.setdefault(key, threading.RLock())


class RuntimeVariables:
    """Lê e grava ``variables.json`` de um único dispositivo."""

    def __init__(self, serial: str, runtime_root: str | Path) -> None:
        if not serial:
            raise ValueError("O serial ADB é obrigatório para criar o ambiente de execução.")
        self.serial = serial
        self.directory = runtime_dir_for(serial, runtime_root)
        self.path = self.directory / "variables.json"
        self._lock = _lock_for(self.path)

    def read_all(self) -> dict[str, Any]:
        with self._lock:
            if not self.path.exists():
                return {}
            try:
                raw = self.path.read_text(encoding="utf-8")
                # Um arquivo vazio pode sobrar de uma interrupção do Windows
                # antes da primeira gravação. Trate-o como ambiente novo, em
                # vez de derrubar uma etapa independente (como enviar mídia).
                # Arquivos preenchidos apenas por NUL podem sobrar de uma
                # interrupção durante a gravação no Windows. Eles não contêm
                # informação aproveitável e não devem bloquear o envio de uma
                # mídia da conta normal.
                if not raw.replace("\x00", "").strip():
                    if "\x00" in raw:
                        temporary = self.path.with_suffix(".json.tmp")
                        temporary.write_text("{}\n", encoding="utf-8")
                        os.replace(temporary, self.path)
                    return {}
                data = json.loads(raw)
            except (OSError, json.JSONDecodeError) as error:
                raise RuntimeError(f"Não foi possível ler {self.path.name}: {error}") from error
            return data if isinstance(data, dict) else {}

    def get(self, name: str, default: Any = None) -> Any:
        return self.read_all().get(name, default)

    def require(self, name: str) -> str:
        value = self.get(name)
        if value is None or str(value).strip() == "":
            raise RuntimeError(f"A variável {{{name}}} ainda não foi criada para o dispositivo {self.serial}.")
        return str(value).strip()

    def set(self, name: str, value: Any) -> None:
        with self._lock:
            data = self.read_all()
            data[name] = value
            temporary = self.path.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temporary, self.path)

    def remove(self, *names: str) -> None:
        """Remove apenas variáveis escolhidas, preservando os demais dados do aparelho."""
        with self._lock:
            data = self.read_all()
            for name in names:
                data.pop(name, None)
            temporary = self.path.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temporary, self.path)

    def expand(self, text: str) -> str:
        values = self.read_all()

        def replace(match: re.Match[str]) -> str:
            key = match.group(1)
            return str(values.get(key, match.group(0)))

        return re.sub(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", replace, text)
