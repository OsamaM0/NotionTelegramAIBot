from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.enums import ChatAction
from aiogram.types import BufferedInputFile, Message

from src.bot.keyboards import chat_keyboard, confirm_action_keyboard
from src.bot.pending_state import (
    clear_confirmation,
    detect_confirmation,
    store_confirmation,
)
from src.bot.utils import safe_send

logger = logging.getLogger(__name__)

router = Router()


def _pick_voice_keyboard(agent, user_id: int, user_role: str, response: str):
    """Confirmation-aware keyboard for voice responses."""
    fields = detect_confirmation(response)
    if fields:
        store_confirmation(user_id, response, fields)
        return confirm_action_keyboard()
    clear_confirmation(user_id)
    return None  # contextual keyboard added after via safe_send


@router.message(F.voice)
async def handle_voice_message(
    message: Message,
    agent,
    user_role: str,
    stt,
    tts,
    bot,
    database,
    **kwargs,
) -> None:
    """Handle voice messages — STT → Agent → TTS response."""
    user_id = message.from_user.id

    # Download voice file
    voice = message.voice
    file = await bot.get_file(voice.file_id)
    voice_data = await bot.download_file(file.file_path)
    audio_bytes = voice_data.read()

    # Transcribe
    await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
    transcribed_text = await stt.transcribe(audio_bytes)

    if not transcribed_text:
        await message.answer("❌ Sorry, I couldn't understand the voice message. Please try again.")
        return

    # Show the transcription
    await message.answer(f"🎤 _{transcribed_text}_", parse_mode="Markdown")

    # Process with agent
    response = await agent.process_message(user_id, user_role, transcribed_text)

    # Send text response with contextual buttons
    kb = _pick_voice_keyboard(agent, user_id, user_role, response)
    if kb is None:
        kb = chat_keyboard()
    await safe_send(message, response, reply_markup=kb)

    # Also send voice response
    try:
        audio_response = await tts.synthesize(response)
        voice_file = BufferedInputFile(audio_response, filename="response.ogg")
        await message.answer_voice(voice_file)
    except Exception as e:
        logger.warning("TTS failed: %s", e)
        # Text response was already sent, so this is non-critical


@router.message(F.audio)
async def handle_audio_message(
    message: Message,
    agent,
    user_role: str,
    stt,
    tts,
    bot,
    database,
    **kwargs,
) -> None:
    """Handle audio file messages (same flow as voice)."""
    user_id = message.from_user.id

    audio = message.audio
    file = await bot.get_file(audio.file_id)
    audio_data = await bot.download_file(file.file_path)
    audio_bytes = audio_data.read()

    await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
    transcribed_text = await stt.transcribe(audio_bytes, filename=audio.file_name or "audio.mp3")

    if not transcribed_text:
        await message.answer("❌ Sorry, I couldn't understand the audio. Please try again.")
        return

    await message.answer(f"🎤 _{transcribed_text}_", parse_mode="Markdown")

    response = await agent.process_message(user_id, user_role, transcribed_text)
    kb = _pick_voice_keyboard(agent, user_id, user_role, response)
    if kb is None:
        kb = chat_keyboard()
    await safe_send(message, response, reply_markup=kb)

    try:
        audio_response = await tts.synthesize(response)
        voice_file = BufferedInputFile(audio_response, filename="response.ogg")
        await message.answer_voice(voice_file)
    except Exception as e:
        logger.warning("TTS failed: %s", e)
