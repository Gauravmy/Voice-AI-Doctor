"""Call entrypoint: decides which agent handles a browser call.

* live -> the Pipecat pipeline (ElevenLabs STT -> Gemini + tools -> ElevenLabs TTS)
* mock -> the rule-based, text-only development receptionist (clearly labelled)
"""

from __future__ import annotations

import json
import logging

from fastapi import WebSocket

from app.config import get_settings

logger = logging.getLogger(__name__)


async def handle_call(websocket: WebSocket) -> None:
    settings = get_settings()
    mode = settings.effective_voice_mode

    if mode == "live" and settings.missing_live_keys:
        await websocket.send_text(json.dumps({
            "type": "error", "fatal": True,
            "message": "Live voice mode is enabled but API keys are missing: "
                       + ", ".join(settings.missing_live_keys),
        }))
        await websocket.close(code=1011)
        return

    if mode == "mock":
        from app.voice.mock_agent import run_mock_call

        logger.info("Starting call in DEVELOPMENT MOCK mode (no external AI services)")
        await run_mock_call(websocket, settings.clinic_name, settings.missing_live_keys)
        return

    from app.voice.pipeline import run_voice_call

    logger.info("Starting live voice call")
    try:
        await run_voice_call(websocket)
    except ValueError as exc:  # e.g. origin rejected by the transport
        logger.warning("Call rejected: %s", exc)
        await websocket.close(code=1008)
    except Exception:
        logger.exception("Voice pipeline crashed")
        try:
            await websocket.send_text(json.dumps({
                "type": "error", "fatal": True,
                "message": "The voice service failed to start. Please try again.",
            }))
            await websocket.close(code=1011)
        except Exception:
            pass
