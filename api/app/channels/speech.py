"""Áudio do WhatsApp: transcrição da entrada e nota de voz da resposta.

A régua não passa por aqui. Sem chave OpenAI, ou com o chat em outro provedor,
a transcrição volta vazia e o turno não inventa o que foi dito.
"""

import hashlib

import httpx

from app.core import storage
from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)

_OPENAI = "https://api.openai.com/v1"
_NOISE = {
    "",
    ".",
    "...",
    "…",
    "[silence]",
    "[silêncio]",
    "[música]",
    "[music]",
    "[aplausos]",
    "[applause]",
    "música",
    "music",
}
_EXT = {
    "audio/ogg": "ogg",
    "audio/opus": "opus",
    "audio/mpeg": "mp3",
    "audio/mp4": "m4a",
    "audio/webm": "webm",
    "audio/wav": "wav",
    "audio/x-m4a": "m4a",
}


def usable_transcript(text: str | None) -> str | None:
    """Frase que pode seguir para intenção e agente. Ruído e vazio não entram."""
    cleaned = " ".join((text or "").replace("\x00", "").split())
    if cleaned.casefold() in _NOISE or len(cleaned) < 2:
        return None
    return cleaned


def _openai_key() -> str | None:
    settings = get_settings()
    if not settings.llm_api_key or not settings.llm_model.startswith("openai:"):
        return None
    return settings.llm_api_key


def stage_voice(tenant_id: str, data: bytes, content_type: str) -> str:
    """Cópia do áudio no storage, fora do caminho de comprovante."""
    mime = content_type.split(";")[0].strip() or "application/octet-stream"
    ext = _EXT.get(mime, "bin")
    key = f"{tenant_id}/voz/{hashlib.sha256(data).hexdigest()}.{ext}"
    storage.put_object(key, data, mime)
    return key


def transcribe(data: bytes, content_type: str) -> str | None:
    key = _openai_key()
    if not key or not data:
        return None
    mime = content_type.split(";")[0].strip() or "audio/ogg"
    ext = _EXT.get(mime, "ogg")
    settings = get_settings()
    try:
        response = httpx.post(
            f"{_OPENAI}/audio/transcriptions",
            headers={"Authorization": f"Bearer {key}"},
            files={"file": (f"audio.{ext}", data, mime)},
            data={"model": settings.stt_model, "language": "pt"},
            timeout=60,
        )
        response.raise_for_status()
        return usable_transcript(response.json().get("text"))
    except Exception:
        log.exception("speech.transcribe_failed")
        return None


def synthesize(text: str) -> bytes | None:
    key = _openai_key()
    spoken = (text or "").strip()
    if not key or not spoken:
        return None
    settings = get_settings()
    try:
        response = httpx.post(
            f"{_OPENAI}/audio/speech",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": settings.tts_model,
                "voice": settings.tts_voice,
                "input": spoken,
                "response_format": "opus",
            },
            timeout=60,
        )
        response.raise_for_status()
        return response.content or None
    except Exception:
        log.exception("speech.synthesize_failed")
        return None


def hear(
    tenant_id: str, instance: str, message_key: dict, raw: dict | None = None,
) -> tuple[str | None, str | None, str | None]:
    """Baixa o áudio, guarda a cópia e devolve (transcrição, media_key, content_type)."""
    from app.channels.whatsapp import EvolutionClient

    try:
        data, mimetype = EvolutionClient().get_media(instance, message_key, raw=raw)
    except Exception:
        log.exception("speech.download_failed")
        return None, None, None
    content_type = (mimetype or "application/octet-stream").split(";")[0].strip()
    media_key = None
    try:
        media_key = stage_voice(tenant_id, data, content_type)
    except Exception:
        log.exception("speech.store_failed")
    return transcribe(data, content_type), media_key, content_type
