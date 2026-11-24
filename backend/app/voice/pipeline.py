"""The real-time Pipecat voice pipeline (one instance per browser call).

    browser mic (PCM16 16 kHz over WebSocket)
      -> transport.input()            FastAPIWebsocketTransport + BrowserAudioSerializer
      -> stt                          ElevenLabs Speech-to-Text (Scribe realtime)
      -> transcript_tap               forwards interim transcripts to the UI
      -> context_aggregator.user()    Silero VAD turn detection, adds user turn to context
      -> llm                          Google Gemini with 3 registered function tools
      -> tts                          ElevenLabs Text-to-Speech (streaming WebSocket)
      -> call_events                  forwards agent text / speaking state to the UI
      -> transport.output()           PCM16 24 kHz back to the browser
      -> context_aggregator.assistant() records the agent turn (+ tool calls) in context
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp
from fastapi import WebSocket
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    Frame,
    InterimTranscriptionFrame,
    LLMRunFrame,
    OutputTransportMessageUrgentFrame,
    TTSTextFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.elevenlabs.stt import ElevenLabsRealtimeSTTService, ElevenLabsSTTService
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.services.google.llm import GoogleLLMService
from pipecat.transcriptions.language import Language
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams, FastAPIWebsocketTransport
from pipecat.workers.runner import WorkerRunner

from app.config import Settings, get_settings
from app.voice.prompts import build_system_prompt
from app.voice.serializer import BrowserAudioSerializer
from app.voice.tools import ClinicTools, build_tools_schema, register_tools

logger = logging.getLogger(__name__)

AUDIO_IN_SAMPLE_RATE = 16000
AUDIO_OUT_SAMPLE_RATE = 24000


class CallEventProcessor(FrameProcessor):
    """Sits just before transport.output(). Turns pipeline activity into small
    JSON events for the browser UI, and gives other code (tools, event
    handlers) an `emit()` method to send their own events on the same socket."""

    async def emit(self, message: dict[str, Any]) -> None:
        await self.push_frame(OutputTransportMessageUrgentFrame(message=message))

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, TTSTextFrame) and direction == FrameDirection.DOWNSTREAM:
            await self.emit({"type": "agent_text", "text": frame.text})
        elif isinstance(frame, BotStartedSpeakingFrame):
            await self.emit({"type": "agent_state", "state": "speaking"})
        elif isinstance(frame, BotStoppedSpeakingFrame):
            await self.emit({"type": "agent_state", "state": "listening"})
        elif isinstance(frame, UserStartedSpeakingFrame) and direction == FrameDirection.DOWNSTREAM:
            await self.emit({"type": "user_state", "state": "speaking"})
        elif isinstance(frame, UserStoppedSpeakingFrame) and direction == FrameDirection.DOWNSTREAM:
            await self.emit({"type": "user_state", "state": "silent"})
        await self.push_frame(frame, direction)


class TranscriptTap(FrameProcessor):
    """Placed right after STT: shows the caller's words in the UI while they speak."""

    def __init__(self, events: CallEventProcessor):
        super().__init__()
        self._events = events

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, InterimTranscriptionFrame) and frame.text.strip():
            await self._events.emit({"type": "transcript", "role": "user",
                                     "text": frame.text, "final": False})
        await self.push_frame(frame, direction)


def _build_stt(settings: Settings, http: aiohttp.ClientSession):
    if settings.elevenlabs_stt_mode == "batch":
        return ElevenLabsSTTService(
            api_key=settings.elevenlabs_api_key, aiohttp_session=http,
            settings=ElevenLabsSTTService.Settings(language=Language.EN),
        )
    return ElevenLabsRealtimeSTTService(
        api_key=settings.elevenlabs_api_key,
        settings=ElevenLabsRealtimeSTTService.Settings(language=Language.EN),
    )


def _build_llm(settings: Settings) -> GoogleLLMService:
    llm_settings: dict[str, Any] = {
        "system_instruction": build_system_prompt(),
        "temperature": 0.3,
    }
    if settings.gemini_model:
        llm_settings["model"] = settings.gemini_model
    return GoogleLLMService(
        api_key=settings.google_api_key,
        settings=GoogleLLMService.Settings(**llm_settings),
        retry_on_timeout=True,
    )


def _build_tts(settings: Settings) -> ElevenLabsTTSService:
    return ElevenLabsTTSService(
        api_key=settings.elevenlabs_api_key,
        settings=ElevenLabsTTSService.Settings(
            voice=settings.elevenlabs_voice_id, model=settings.elevenlabs_tts_model,
        ),
    )


def build_voice_call(
    websocket: WebSocket, http: aiohttp.ClientSession, settings: Settings
) -> PipelineWorker:
    """Construct (but do not start) the pipeline for one call. No network I/O
    happens here, which lets tests verify the wiring without API keys."""
    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            serializer=BrowserAudioSerializer(),
            session_timeout=settings.call_max_duration_secs,
            allowed_origins=settings.cors_origin_list,
        ),
    )

    call_events = CallEventProcessor()
    tools = ClinicTools(emit=call_events.emit)

    stt = _build_stt(settings, http)
    llm = _build_llm(settings)
    tts = _build_tts(settings)
    register_tools(llm, tools, timeout_secs=settings.tool_timeout_secs)

    context = LLMContext(tools=build_tools_schema())
    aggregators = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.5)),
        ),
    )

    pipeline = Pipeline([
        transport.input(),
        stt,
        TranscriptTap(call_events),
        aggregators.user(),
        llm,
        tts,
        call_events,
        transport.output(),
        aggregators.assistant(),
    ])

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=AUDIO_IN_SAMPLE_RATE,
            audio_out_sample_rate=AUDIO_OUT_SAMPLE_RATE,
            enable_metrics=True,
        ),
        enable_rtvi=False,  # we use our own minimal JSON protocol (serializer.py)
        idle_timeout_secs=settings.call_idle_timeout_secs,
    )

    @aggregators.user().event_handler("on_user_turn_stopped")
    async def on_user_turn_stopped(_aggregator, _strategy, message):
        if message.content:
            await call_events.emit({"type": "transcript", "role": "user",
                                    "text": message.content, "final": True})

    @aggregators.assistant().event_handler("on_assistant_turn_stopped")
    async def on_assistant_turn_stopped(_aggregator, message):
        if message.content:
            await call_events.emit({"type": "transcript", "role": "agent",
                                    "text": message.content, "final": True,
                                    "interrupted": message.interrupted})

    @transport.event_handler("on_client_connected")
    async def on_client_connected(_transport, _ws):
        logger.info("Voice call connected")
        await call_events.emit({"type": "call_state", "state": "connected", "mode": "live"})
        await worker.queue_frames([LLMRunFrame()])  # the agent greets the caller

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(_transport, _ws):
        logger.info("Voice call disconnected by client")
        await worker.cancel()

    @transport.event_handler("on_session_timeout")
    async def on_session_timeout(_transport, _ws):
        logger.info("Voice call reached the maximum duration")
        await worker.cancel()

    reported: set[tuple[str, bool]] = set()

    @worker.event_handler("on_pipeline_error")
    async def on_pipeline_error(_worker, frame):
        """Tell the caller's UI which service failed (once per service), and end
        the call cleanly if a service can no longer work (e.g. API key rejected)."""
        processor = getattr(frame, "processor", None)
        usable = bool(getattr(processor, "is_usable", True))
        fatal = bool(getattr(frame, "fatal", False)) or not usable
        service = _service_label(processor)
        logger.error("Pipeline error in %s (usable=%s): %s", service, usable,
                     getattr(frame, "error", frame))
        key = (service, fatal)
        if key in reported:
            return
        reported.add(key)
        await call_events.emit({
            "type": "error",
            "fatal": fatal,
            "message": (f"The {service} service stopped working (check its API key, model and quota). "
                        "The call has been ended." if fatal
                        else f"The {service} service reported an error; retrying."),
        })
        if fatal:
            async def end_call():
                await asyncio.sleep(0.5)  # let the error event reach the browser
                await worker.cancel(reason=f"{service} unusable")
            asyncio.create_task(end_call())

    return worker


def _service_label(processor: Any) -> str:
    name = type(processor).__name__ if processor is not None else ""
    if "STT" in name:
        return "speech-to-text (ElevenLabs)"
    if "TTS" in name:
        return "text-to-speech (ElevenLabs)"
    if "LLM" in name:
        return "language model (Gemini)"
    return "voice"


async def run_voice_call(websocket: WebSocket) -> None:
    """Build and run the pipeline for one call; returns when the call ends."""
    settings = get_settings()
    if settings.missing_live_keys:
        raise RuntimeError(f"Live voice mode needs: {', '.join(settings.missing_live_keys)}")
    async with aiohttp.ClientSession() as http:
        worker = build_voice_call(websocket, http, settings)
        runner = WorkerRunner(handle_sigint=False)
        await runner.add_workers(worker)
        await runner.run()  # returns when the call's pipeline finishes
    logger.info("Voice call pipeline finished")
