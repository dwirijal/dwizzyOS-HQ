"""Media generation tools — text-to-image, TTS, STT via 9router API.

These are FunctionTools that call 9router's native multimodal capabilities.
Agents can generate images, audio, and transcribe speech as part of their workflows.
"""
from __future__ import annotations

import os
import requests
from google.adk.tools import FunctionTool

from shared.config import ROUTER_BASE_URL, ROUTER_API_KEY


def generate_image(prompt: str, size: str = "1024x1024") -> dict:
    """Generate an image from text description using 9router's image models.

    Args:
        prompt: Text description of the image to generate
        size: Image dimensions (e.g., "1024x1024", "512x512")

    Returns:
        dict with 'url' (if available) or 'base64' image data
    """
    key = ROUTER_API_KEY or os.environ.get("OPENAI_API_KEY", "")

    # 9router supports DALL-E compatible endpoint
    resp = requests.post(
        f"{ROUTER_BASE_URL}/images/generations",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"
        },
        json={
            "model": "dall-e-3",  # or other supported image models
            "prompt": prompt,
            "size": size,
            "n": 1
        },
        timeout=60
    )

    if resp.status_code != 200:
        return {"error": f"Image generation failed: {resp.text}"}

    data = resp.json()
    return {"url": data["data"][0].get("url"), "revised_prompt": data["data"][0].get("revised_prompt")}


def text_to_speech(text: str, voice: str = "alloy") -> dict:
    """Convert text to speech audio using 9router's TTS models.

    Args:
        text: Text to convert to speech
        voice: Voice model to use (e.g., "alloy", "echo", "fable", "onyx", "nova", "shimmer")

    Returns:
        dict with 'audio_data' (base64) or 'url' to audio file
    """
    key = ROUTER_API_KEY or os.environ.get("OPENAI_API_KEY", "")

    resp = requests.post(
        f"{ROUTER_BASE_URL}/audio/speech",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"
        },
        json={
            "model": "tts-1",  # or tts-1-hd for higher quality
            "input": text,
            "voice": voice
        },
        timeout=60
    )

    if resp.status_code != 200:
        return {"error": f"TTS failed: {resp.text}"}

    # Audio data is returned as bytes, base64 encode for JSON
    import base64
    audio_b64 = base64.b64encode(resp.content).decode("utf-8")
    return {"audio_data": audio_b64, "format": "mp3"}


def speech_to_text(audio_base64: str, language: str = "en") -> dict:
    """Transcribe speech audio to text using 9router's STT models.

    Args:
        audio_base64: Base64-encoded audio data (mp3, wav, etc.)
        language: Language code (e.g., "en", "es", "fr", "id")

    Returns:
        dict with 'text' transcription
    """
    key = ROUTER_API_KEY or os.environ.get("OPENAI_API_KEY", "")

    # Decode base64 to bytes
    import base64
    audio_bytes = base64.b64decode(audio_base64)

    # Whisper API expects multipart form data
    files = {
        "file": ("audio.mp3", audio_bytes, "audio/mpeg")
    }
    data = {
        "model": "whisper-1",
        "language": language
    }

    resp = requests.post(
        f"{ROUTER_BASE_URL}/audio/transcriptions",
        headers={"Authorization": f"Bearer {key}"},
        files=files,
        data=data,
        timeout=60
    )

    if resp.status_code != 200:
        return {"error": f"STT failed: {resp.text}"}

    return {"text": resp.json().get("text")}


# Export as FunctionTools
generate_image_tool = FunctionTool(func=generate_image)
text_to_speech_tool = FunctionTool(func=text_to_speech)
speech_to_text_tool = FunctionTool(func=speech_to_text)
