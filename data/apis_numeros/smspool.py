"""Integração da API SMSPool para o iggents.

Contrato de uma API de números:
  - order_number(config, service, country, max_price) -> dict com order_id e number/phonenumber
  - wait_for_code(config, order_id, timeout_s, cancel_event) -> código recebido

A chave é mantida em configuracoes.json, no perfil da API, e não neste arquivo.
"""

from tools.smspool import SMSPoolClient


def order_number(config: dict, service: str, country: str, max_price: float | None = None) -> dict:
    return SMSPoolClient(str(config.get("api_key", ""))).order_sms(service, country, max_price)


def wait_for_code(config: dict, order_id: str, timeout_s: int, cancel_event=None) -> str:
    return SMSPoolClient(str(config.get("api_key", ""))).wait_for_sms(order_id, timeout_s, cancel_event)
