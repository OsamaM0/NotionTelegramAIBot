from __future__ import annotations

import io
import logging

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class SpeechToText:
    """Convert voice messages to text using OpenAI Whisper."""

    def __init__(self, api_key: str, model: str = "whisper-1") -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    async def transcribe(self, audio_data: bytes, filename: str = "voice.ogg") -> str:
        """Transcribe audio bytes to text.

        Args:
            audio_data: Raw audio file bytes (OGG from Telegram).
            filename: Filename hint for the API.

        Returns:
            Transcribed text.
        """
        audio_file = io.BytesIO(audio_data)
        audio_file.name = filename

        response = await self._client.audio.transcriptions.create(
            model=self._model,
            file=audio_file,
        )
        text = response.text.strip()
        logger.info("Transcribed voice message: %d chars", len(text))
        return text
