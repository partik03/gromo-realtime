#
# Copyright (c) 2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import os
import sys

from dotenv import load_dotenv
from loguru import logger
from pipecat.processors.audio.audio_buffer_processor import AudioBufferProcessor
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.observers.loggers.transcription_log_observer import TranscriptionLogObserver
from pipecat.services.openai.stt import OpenAISTTService

# from app.plivo import PlivoFrameSerializer
from serializers.exotel import ExotelFrameSerializer
# from pipecat.services.cartesia import CartesiaTTSService
# from pipecat.services.elevenlabs import ElevenLabsTTSService
# from pipecat.services.deepgram.stt import DeepgramSTTService

# from pipecat.services.openai.llm import OpenAILLMService
from groq_service.llm import OpenAILLMService
from pipecat.audio.mixers.soundfile_mixer import SoundfileMixer
from pipecat.processors.transcript_processor import TranscriptProcessor
from pipecat.transports.network.fastapi_websocket import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)
import wave 
import io 
import datetime
import aiofiles
# from pipecat.observers.loggers.debug_log_observer import DebugLogObserver




load_dotenv(override=True)

# Remove this line or modify it
# logger.remove(0)  # This line causes the error

# Instead, if you want to remove all handlers, use:
logger.remove()

# Or if you want to configure a new handler:
logger.add(sys.stderr, format="{time} {level} {message}", level="INFO")
logger.add(sys.stderr, level="DEBUG")


class TranscriptHandler:
    def __init__(self):
        self.messages = []

    async def on_transcript_update(self, processor, frame):
        self.messages.extend(frame.messages)

        # Log new messages with timestamps
        for msg in frame.messages:
            timestamp = f"[{msg.timestamp}] " if msg.timestamp else ""
            print(f"TTTT: {timestamp}{msg.role}: {msg.content}")


async def run_bot(websocket_client, stream_sid):
    mixer = SoundfileMixer(
        sound_files={
            "office": os.path.join(os.path.dirname(__file__), "office_ambience.wav")
        },
        default_sound="office",
        volume=1.0,
    )
    audiobuffer = AudioBufferProcessor(
        sample_rate=8000,  # Match Exotel's sample rate
        num_channels=1,    # Mono audio
        buffer_size=0,     # Size in bytes to trigger buffer callbacks
        audio_in_passthrough=True,  # Pass through the audio without modification
        resample=False,  # Disable resampling
        accumulate=False,  # Disable accumulation
        max_buffer_size=0  # No maximum buffer size
    )

    transport = FastAPIWebsocketTransport(
        websocket=websocket_client,
        params=FastAPIWebsocketParams(
            audio_out_enabled=True,
            add_wav_header=False,
            audio_in_enabled=True,
            vad_analyzer=SileroVADAnalyzer(
                sample_rate=8000,  # Match Exotel's sample rate
                params=VADParams(
                    stop_secs=1.0,      # How long to wait after speech stops
                    start_secs=0.2,     # How long before considering speech started
                    min_volume=0.6      # Minimum volume threshold (0.0-1.0)
                )
            ),
            serializer=ExotelFrameSerializer(stream_sid),
            audio_out_mixer=mixer,
        ),
    )

    # llm = OpenAILLMService(api_key=os.getenv("OPENAI_API_KEY"), model="gpt-4o-mini")
    llm = OpenAILLMService(api_key=os.getenv("GROQ_API_KEY"), model="meta-llama/llama-4-maverick-17b-128e-instruct", stream=True)

    stt = OpenAISTTService(
        api_key=os.getenv("OPENAI_API_KEY"),
        model="gpt-4o-transcribe",
        prompt= "This is a recorded call between a GroMo Partner and a GroMo Sales Agent. "
    "Transcribe the conversation accurately in Hindi. Clearly identify and label the two speakers as 'Partner:' and 'Agent:' throughout the transcription. "
    "The Partner is a field representative or user of the GroMo app trying to sell financial products. "
    "The Agent is assisting or training the Partner, answering questions, and providing support. "
    "Ensure accurate speaker attribution and preserve the natural flow of the conversation."
,
        language="hi"
    )

    messages = [
        {
            "role": "system",
            "content": "You are an AI assistant analyzing a live Hindi call between a GroMo Partner (field agent) and a GroMo Sales Agent (trainer/support). "
    "Given the following transcript chunk, analyze the conversation and provide:\n\n"
    "1. Who is speaking more in this segment: Partner or Agent?\n"
    "2. What is the confidence level of the Partner? (Low / Medium / High) — justify in 1 line.\n"
    "3. Is the Partner confused or asking repetitive questions? (Yes/No) — give short reason.\n"
    "4. Is the Agent being clear and helpful? (Yes/No)\n"
    "5. What is the Partner's main concern or question? (intent)\n"
    "6. Was any resolution or next action offered? (Yes/No)\n"
    "7. Suggest 1 short training topic the Partner needs help with.\n"
    "8. 💬 What should the Agent say next to help the Partner understand better? Write a 1-line example response in Hindi.\n"
    "9. ❓ What should the Agent ask next to keep the conversation moving forward? Give a 1-line question in Hindi.\n"
    "10. Confidence score (0–100) of your analysis.\n\n"
    "Transcript:\n",
        },
    ]
    context = OpenAILLMContext(messages)
    context_aggregator = llm.create_context_aggregator(context)

    transcript = TranscriptProcessor()

    pipeline = Pipeline(
        [
            transport.input(),  # Websocket input from client
            stt,  # Speech-To-Text
            transcript.user(),
            audiobuffer,
            context_aggregator.user(),
            llm,  # LLM
            # tts,  # Text-To-Speech
            transport.output(),  # Websocket output to client
            context_aggregator.assistant(),
            transcript.assistant(),
        ]
    )

    task = PipelineTask(pipeline, params=PipelineParams(allow_interruptions=True, observers=[TranscriptionLogObserver()]))

    handler = TranscriptHandler()

    @transcript.event_handler("on_transcript_update")
    async def on_update(processor, frame):
        logger.info(f"Transcript update: {frame.messages}")
        await handler.on_transcript_update(processor, frame)

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Client connected successfully")
        # Kick off the conversation.
        # messages.append(
        #     {"role": "system", "content": "Please introduce yourself to the user."}
        # )
        await audiobuffer.start_recording()
        await task.queue_frames([context_aggregator.user().get_context_frame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        await audiobuffer.stop_recording()
        await task.cancel()
    
    async def save_audio(audio: bytes, sample_rate: int, num_channels: int):
        if len(audio) > 0:
            filename = f"./recordings/conversation_recording{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
            with io.BytesIO() as buffer:
                with wave.open(buffer, "wb") as wf:
                    wf.setsampwidth(2)  # 16-bit PCM
                    wf.setnchannels(num_channels)
                    wf.setframerate(sample_rate)
                    # Ensure audio is in the correct format
                    if isinstance(audio, bytes):
                        wf.writeframes(audio)
                    else:
                        # Convert numpy array to bytes if needed
                        audio_bytes = audio.tobytes() if hasattr(audio, 'tobytes') else bytes(audio)
                        wf.writeframes(audio_bytes)
                async with aiofiles.open(filename, "wb") as file:
                    await file.write(buffer.getvalue())
            print(f"Merged audio saved to {filename}")

    # Handle the recorded audio chunks
    @audiobuffer.event_handler("on_audio_data")
    async def on_audio_data(buffer, audio, sample_rate, num_channels):
        logger.info(f"Audio data received: {len(audio)} bytes at {sample_rate} Hz with {num_channels} channels")
        await save_audio(audio, sample_rate, num_channels)

    runner = PipelineRunner(handle_sigint=False)

    await runner.run(task)