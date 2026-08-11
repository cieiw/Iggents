"""Driver da 5sim.net para o iggents.

O token fica no perfil local da API, nunca neste arquivo.  Contrato:
``order_number(config, product, country, max_price)`` e
``wait_for_code(config, order_id, timeout_s, cancel_event)``.
"""

from __future__ import annotations

import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


BASE_URL = "https://5sim.net/v1/user"


def _request(config: dict, endpoint: str) -> dict:
    token = str(config.get("api_key", "")).strip()
    if not token:
        raise RuntimeError("informe o token da 5sim.net em APIs de número")
    request = Request(
        f"{BASE_URL}{endpoint}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace").strip()
        raise RuntimeError(detail or f"HTTP {error.code}") from error
    except URLError as error:
        raise RuntimeError(f"falha de rede: {error.reason}") from error
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"resposta inválida da 5sim: {raw[:180]}") from error
    if not isinstance(data, dict):
        raise RuntimeError("resposta inválida da 5sim")
    return data


def _error_message(data: dict) -> str:
    for key in ("message", "error", "detail", "status"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "a 5sim não retornou um pedido válido"


def order_number(config: dict, service: str, country: str, max_price: float | None = None) -> dict:
    product = str(service or "").strip().casefold()
    chosen_country = str(country or "any").strip().casefold()
    operator = str(config.get("operator") or "any").strip().casefold()
    if not product:
        raise RuntimeError("informe o produto da 5sim, por exemplo instagram")
    if not chosen_country:
        raise RuntimeError("informe o país da 5sim, por exemplo brazil ou any")
    if not operator:
        operator = "any"
    params = ""
    if max_price and float(max_price) > 0:
        params = f"?maxPrice={quote(str(float(max_price)), safe='.') }"
    result = _request(
        config,
        f"/buy/activation/{quote(chosen_country, safe='')}/{quote(operator, safe='')}/{quote(product, safe='')}{params}",
    )
    order_id = result.get("id")
    phone = str(result.get("phone") or "").strip()
    if not order_id or not phone:
        raise RuntimeError(_error_message(result))
    return {"order_id": str(order_id), "number": phone, "phonenumber": phone, "raw": result}


def wait_for_code(config: dict, order_id: str, timeout_s: int, cancel_event=None) -> str:
    deadline = time.monotonic() + max(10, int(timeout_s))
    last_status = ""
    while time.monotonic() < deadline:
        if cancel_event is not None and cancel_event.is_set():
            return ""
        result = _request(config, f"/check/{quote(str(order_id), safe='')}")
        messages = result.get("sms")
        if isinstance(messages, list):
            for message in reversed(messages):
                if isinstance(message, dict) and str(message.get("code") or "").strip():
                    return str(message["code"]).strip()
        status = str(result.get("status") or "").upper()
        if status in {"CANCELED", "CANCELLED", "FINISHED", "TIMEOUT", "EXPIRED"}:
            raise RuntimeError(f"pedido {order_id} encerrado pela 5sim ({status})")
        last_status = status or last_status
        if cancel_event is not None:
            if cancel_event.wait(3):
                return ""
        else:
            time.sleep(3)
    raise RuntimeError(f"nenhum SMS recebido em {timeout_s}s" + (f" (estado: {last_status})" if last_status else ""))


def check_code(config: dict, order_id: str) -> str:
    """Consulta uma única vez o pedido atual, sem aguardar SMS."""
    result = _request(config, f"/check/{quote(str(order_id), safe='')}")
    messages = result.get("sms")
    if isinstance(messages, list):
        for message in reversed(messages):
            if isinstance(message, dict) and str(message.get("code") or "").strip():
                return str(message["code"]).strip()
    status = str(result.get("status") or "").upper()
    if status in {"CANCELED", "CANCELLED", "FINISHED", "TIMEOUT", "EXPIRED"}:
        raise RuntimeError(f"pedido {order_id} encerrado pela 5sim ({status})")
    return ""


def finish_order(config: dict, order_id: str) -> None:
    """Marca o pedido como concluído depois de o código ser digitado."""
    _request(config, f"/finish/{quote(str(order_id), safe='')}")
