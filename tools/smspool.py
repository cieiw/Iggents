"""Cliente mínimo para pedidos de SMS de uso único no SMSPool."""

from __future__ import annotations

import json
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API_ROOT = "https://api.smspool.net"


class SMSPoolClient:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key.strip()
        if not self.api_key:
            raise RuntimeError("Configure a chave da API SMSPool antes de executar a macro.")

    def _post(self, path: str, **data) -> dict | list:
        data["key"] = self.api_key
        request = Request(
            f"{API_ROOT}{path}", data=urlencode(data).encode("utf-8"), method="POST",
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        try:
            with urlopen(request, timeout=25) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            detail = error.read().decode("utf-8", "replace")
            try:
                detail = json.loads(detail).get("message", detail)
            except json.JSONDecodeError:
                pass
            raise RuntimeError(f"SMSPool respondeu {error.code}: {detail}") from error
        except (URLError, TimeoutError) as error:
            raise RuntimeError(f"Não consegui acessar o SMSPool: {error}") from error
        if isinstance(payload, dict) and not payload.get("success", 1):
            message = payload.get("message") or "; ".join(item.get("message", "") for item in payload.get("errors", []))
            raise RuntimeError(f"SMSPool não concluiu a solicitação: {message or 'sem detalhe'}")
        return payload

    def order_sms(self, service: str, country: str, max_price: float | None = None) -> dict:
        data = {"service": service, "country": country, "quantity": 1, "activation_type": "SMS"}
        if max_price is not None:
            data["max_price"] = f"{max_price:.2f}"
        order = self._post("/purchase/sms", **data)
        if not isinstance(order, dict) or not order.get("order_id"):
            raise RuntimeError("O SMSPool não retornou os dados do pedido.")
        return order

    def wait_for_sms(self, order_id: str, timeout_s: int, cancel_event=None) -> str:
        end_at = time.monotonic() + max(10, timeout_s)
        while time.monotonic() < end_at:
            if cancel_event and cancel_event.is_set():
                raise RuntimeError("Busca do SMSPool interrompida.")
            # O próprio SMSPool recomenda consultar os pedidos ativos em vez
            # de fazer somente verificações individuais em alta frequência.
            active_orders = self._post("/request/active")
            if isinstance(active_orders, list):
                for active in active_orders:
                    if str(active.get("order_code", active.get("order_id", ""))) == order_id:
                        code = self._extract_code(active)
                        if code:
                            return code
            result = self._post("/sms/check", orderid=order_id)
            if not isinstance(result, dict):
                raise RuntimeError("Resposta inválida do SMSPool.")
            code = self._extract_code(result)
            if code:
                return code
            if result.get("status") in (2, 5, 6):
                raise RuntimeError(str(result.get("message") or "O pedido expirou, foi cancelado ou reembolsado."))
            time.sleep(3)
        raise RuntimeError("O SMSPool não entregou o código dentro do tempo configurado.")

    @staticmethod
    def _extract_code(result: dict) -> str:
        """Normaliza as duas formas de resposta de código do SMSPool."""
        for field in ("sms", "code", "full_sms", "full_code"):
            value = str(result.get(field) or "").strip()
            if not value or value == "0":
                continue
            match = re.search(r"\b\d{4,8}\b", value)
            return match.group(0) if match else value
        return ""
