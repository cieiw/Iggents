"""Modelo para adicionar outra API de números ao iggents.

Copie este arquivo, implemente as duas funções e adicione-o em
APIs de número > Nova API por script.

``config`` contém os dados salvos no perfil (por padrão, ``api_key``).
``cancel_event`` deve ser consultado durante a espera pelo SMS.
"""


def order_number(config: dict, service: str, country: str, max_price: float | None = None) -> dict:
    """Compre/alugue um número.

    Retorne ao menos:
        {"order_id": "id-do-pedido", "number": "telefone-sem-formatacao"}
    Também é aceito ``phonenumber`` no lugar de ``number``.
    """
    raise NotImplementedError("Implemente a compra de número desta API.")


def wait_for_code(config: dict, order_id: str, timeout_s: int, cancel_event=None) -> str:
    """Aguarde e retorne apenas o código recebido."""
    raise NotImplementedError("Implemente a consulta do código desta API.")
