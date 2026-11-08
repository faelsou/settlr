"""Canal WhatsApp via Evolution API: envio, leitura do webhook e debounce no Redis."""

import base64
import json
import time
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.redis import get_redis
from app.dunning.official import parse_connection_state, parse_template_catalog

GROUP_SUFFIX = "@g.us"
MEDIA_TYPES = {"imageMessage", "documentMessage", "documentWithCaptionMessage"}


class EvolutionWebhook(BaseModel):
    event: str
    instance: str
    data: dict[str, Any] | list[Any]


@dataclass(frozen=True)
class InboundMessage:
    instance: str
    message_id: str
    remote_jid: str
    from_me: bool
    push_name: str | None
    text: str | None
    media_type: str | None
    mimetype: str | None
    key: dict[str, Any]
    timestamp: int
    quoted_id: str | None = None

    @property
    def is_group(self) -> bool:
        return self.remote_jid.endswith(GROUP_SUFFIX)

    @property
    def phone(self) -> str:
        return self.remote_jid.split("@", 1)[0]

    @property
    def has_media(self) -> bool:
        return self.media_type is not None

    def to_json(self) -> str:
        return json.dumps(self.__dict__)

    @classmethod
    def from_json(cls, raw: str) -> "InboundMessage":
        data = json.loads(raw)
        data.setdefault("quoted_id", None)
        return cls(**data)


def _contact_jid(key: dict[str, Any]) -> str:
    """O WhatsApp entrega a resposta num identificador interno (@lid). O telefone
    real vem em remoteJidAlt e é o que casa com o cadastro do devedor."""
    remote = key.get("remoteJid") or ""
    alt = key.get("remoteJidAlt") or ""
    if remote.endswith("@lid") and alt:
        return alt
    return remote


def quoted_stanza_id(data: dict[str, Any]) -> str | None:
    """Id da mensagem citada quando a pessoa responde em cima de um envio nosso."""
    message = data.get("message") or {}
    contexts = (
        data.get("contextInfo"),
        message.get("contextInfo"),
        (message.get("extendedTextMessage") or {}).get("contextInfo"),
    )
    for ctx in contexts:
        stanza = ctx.get("stanzaId") if isinstance(ctx, dict) else None
        if stanza:
            return str(stanza)
    return None


def inbound_from_record(instance: str, raw: dict[str, Any]) -> InboundMessage | None:
    """Converte um registro do findMessages (ou o `data` do webhook) em InboundMessage."""
    data = raw.get("data") if isinstance(raw.get("data"), dict) and "key" in (raw.get("data") or {}) else raw
    if not isinstance(data, dict) or not data.get("key"):
        return None
    return parse_inbound(EvolutionWebhook(event="messages.upsert", instance=instance, data=data))


def parse_inbound(payload: EvolutionWebhook) -> InboundMessage | None:
    if payload.event.lower().replace("_", ".") != "messages.upsert":
        return None
    if not isinstance(payload.data, dict):
        return None
    data = payload.data
    key = data.get("key") or {}
    message = data.get("message") or {}

    text = (
        message.get("conversation")
        or (message.get("extendedTextMessage") or {}).get("text")
    )
    media_type = next((t for t in MEDIA_TYPES if t in message), None)
    mimetype = None
    if media_type:
        media = message[media_type]
        if media_type == "documentWithCaptionMessage":
            media = media.get("message", {}).get("documentMessage", {})
        mimetype = media.get("mimetype")
        text = text or media.get("caption")

    return InboundMessage(
        instance=payload.instance,
        message_id=key.get("id", ""),
        remote_jid=_contact_jid(key),
        from_me=bool(key.get("fromMe")),
        push_name=data.get("pushName"),
        text=text,
        media_type=media_type,
        mimetype=mimetype,
        key=key,
        timestamp=int(data.get("messageTimestamp") or time.time()),
        quoted_id=quoted_stanza_id(data),
    )


class EvolutionClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        settings = get_settings()
        self._client = httpx.Client(
            base_url=base_url or settings.evolution_base_url,
            headers={"apikey": api_key or settings.evolution_api_key},
            timeout=30,
        )

    def find_chats(self, instance: str) -> list[dict[str, Any]]:
        response = self._client.post(f"/chat/findChats/{instance}", json={})
        response.raise_for_status()
        body = response.json()
        return body if isinstance(body, list) else body.get("chats") or body.get("records") or []

    def find_messages(self, instance: str, remote_jid: str, limit: int = 20) -> list[dict[str, Any]]:
        response = self._client.post(
            f"/chat/findMessages/{instance}",
            json={"where": {"key": {"remoteJid": remote_jid}}, "limit": limit},
        )
        response.raise_for_status()
        messages = response.json().get("messages") or {}
        return messages.get("records") or []

    def connection_state(self, instance: str) -> str | None:
        """`open` significa número pareado. Qualquer outro estado deixa a régua desligada."""
        response = self._client.get(f"/instance/connectionState/{instance}")
        response.raise_for_status()
        return parse_connection_state(response.json())

    def list_templates(self, instance: str) -> list[dict[str, Any]]:
        """Templates da conta na Meta. A régua só aceita status `approved`."""
        response = self._client.get(f"/template/find/{instance}")
        response.raise_for_status()
        return parse_template_catalog(response.json())

    def send_text(self, instance: str, number: str, text: str) -> str | None:
        response = self._client.post(
            f"/message/sendText/{instance}", json={"number": number, "text": text}
        )
        response.raise_for_status()
        return (response.json().get("key") or {}).get("id")

    def send_template(
        self, instance: str, number: str, name: str, language: str, params: list[str]
    ) -> str | None:
        """Template oficial (WhatsApp Business API) para disparo proativo."""
        body = {
            "number": number,
            "name": name,
            "language": language,
            "components": [
                {"type": "body", "parameters": [{"type": "text", "text": p} for p in params]}
            ],
        }
        response = self._client.post(f"/message/sendTemplate/{instance}", json=body)
        response.raise_for_status()
        return (response.json().get("key") or {}).get("id")

    def get_media(
        self, instance: str, key: dict[str, Any], raw: dict[str, Any] | None = None
    ) -> tuple[bytes, str]:
        message = raw if raw and raw.get("key") else {"key": key}
        response = self._client.post(
            f"/chat/getBase64FromMediaMessage/{instance}",
            json={"message": message, "convertToMp4": False},
        )
        response.raise_for_status()
        body = response.json()
        return base64.b64decode(body["base64"]), body.get("mimetype", "application/octet-stream")


def debounce_push(tenant_id: str, msg: InboundMessage) -> str:
    """Acumula a mensagem na rajada do contato e devolve a chave do buffer."""
    r = get_redis()
    buffer_key = f"debounce:{tenant_id}:{msg.remote_jid}"
    window = get_settings().inbound_debounce_seconds
    pipe = r.pipeline()
    pipe.rpush(buffer_key, msg.to_json())
    pipe.expire(buffer_key, window * 10)
    pipe.set(f"{buffer_key}:last", time.time(), ex=window * 10)
    pipe.execute()
    return buffer_key


def debounce_drain(buffer_key: str) -> list[InboundMessage] | None:
    """Esvazia o buffer se a rajada terminou. None = ainda chegando mensagem;
    uma task agendada mais tarde vai drenar."""
    r = get_redis()
    window = get_settings().inbound_debounce_seconds
    last = r.get(f"{buffer_key}:last")
    if last is not None and time.time() - float(last) < window:
        return None
    pipe = r.pipeline()
    pipe.lrange(buffer_key, 0, -1)
    pipe.delete(buffer_key, f"{buffer_key}:last")
    raw, _ = pipe.execute()
    return [InboundMessage.from_json(item) for item in raw]
