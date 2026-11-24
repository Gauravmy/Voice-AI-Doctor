"""Wire protocol between the browser and the Pipecat pipeline.

A deliberately tiny protocol, easy to read and to implement in the browser:

Browser -> server
    binary frame : raw PCM16 little-endian mono audio at 16 kHz (microphone)
    text frame   : JSON control message, e.g. {"type": "end_call"}

Server -> browser
    binary frame : raw PCM16 little-endian mono audio at the pipeline's output
                   rate (24 kHz) - the agent's synthesized voice
    text frame   : JSON event, e.g. {"type": "transcript", ...}
                   {"type": "interrupt"} tells the browser to drop queued audio
                   because the caller started speaking (barge-in).
"""

from __future__ import annotations

import json

from loguru import logger
from pipecat.frames.frames import (
    Frame,
    InputAudioRawFrame,
    InputTransportMessageFrame,
    InterruptionFrame,
    OutputAudioRawFrame,
    OutputTransportMessageFrame,
    OutputTransportMessageUrgentFrame,
)
from pipecat.serializers.base_serializer import FrameSerializer

BROWSER_INPUT_SAMPLE_RATE = 16000


class BrowserAudioSerializer(FrameSerializer):
    def __init__(self) -> None:
        super().__init__(FrameSerializer.InputParams(ignore_rtvi_messages=True))

    async def serialize(self, frame: Frame) -> str | bytes | None:
        if isinstance(frame, OutputAudioRawFrame):
            return frame.audio
        if isinstance(frame, InterruptionFrame):
            return json.dumps({"type": "interrupt"})
        if isinstance(frame, (OutputTransportMessageFrame, OutputTransportMessageUrgentFrame)):
            if self.should_ignore_frame(frame):
                return None
            return json.dumps(frame.message)
        return None

    async def deserialize(self, data: str | bytes) -> Frame | None:
        if isinstance(data, (bytes, bytearray)):
            if len(data) % 2:  # PCM16 must be an even number of bytes
                return None
            return InputAudioRawFrame(
                audio=bytes(data), sample_rate=BROWSER_INPUT_SAMPLE_RATE, num_channels=1
            )
        try:
            message = json.loads(data)
        except (json.JSONDecodeError, TypeError):
            logger.warning("Ignoring malformed control message from browser")
            return None
        if not isinstance(message, dict):
            return None
        return InputTransportMessageFrame(message=message)
