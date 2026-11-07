"""Um turno do agente por mensagem de entrada.

O webhook e a reconciliação usam a mesma chave. O segundo a chegar não
responde de novo.
"""

from uuid import UUID

from app.core.redis import get_redis


def _key(conversation_id: UUID, token: str) -> str:
    return f"agent:turn:{conversation_id}:{token}"


def claim_turn(conversation_id: UUID, token: str) -> bool:
    if not token:
        return False
    return bool(get_redis().set(_key(conversation_id, token), "1", nx=True, ex=600))


def release_turn(conversation_id: UUID, token: str) -> None:
    if token:
        get_redis().delete(_key(conversation_id, token))


def claim_once(token: str) -> bool:
    """Trava global por id de mensagem. Webhook e reconciliação compartilham."""
    if not token:
        return False
    return bool(get_redis().set(f"once:{token}", "1", nx=True, ex=600))


def release_once(token: str) -> None:
    if token:
        get_redis().delete(f"once:{token}")
