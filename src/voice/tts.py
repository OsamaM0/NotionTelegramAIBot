from __future__ import annotations

import logging

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class TextToSpeech:
    """Convert text to voice messages using OpenAI TTS."""

    def __init__(self, api_key: str, model: str = "tts-1", voice: str = "alloy") -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model
        self._voice = voice

    async def synthesize(self, text: str) -> bytes:
        """Convert text to OGG opus audio (Telegram voice format).

        Args:
            text: Text to convert to speech.

        Returns:
            OGG opus audio bytes ready for Telegram.
        """
        # Truncate very long text to avoid TTS limits
        if len(text) > 4096:
            text = text[:4093] + "..."

        response = await self._client.audio.speech.create(
            model=self._model,
            voice=self._voice,
            input=text,
            response_format="opus",
        )

        audio_bytes = response.content
        logger.info("Generated TTS audio: %d bytes", len(audio_bytes))
        return audio_bytes
