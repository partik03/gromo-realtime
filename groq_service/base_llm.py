#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import json
from typing import Any, Dict, List, Mapping, Optional

import httpx
from loguru import logger
from groq import AsyncGroq
from pydantic import BaseModel, Field


from openai import AsyncStream
from openai.types.chat import ChatCompletionChunk
from openai.types.completion_usage import CompletionUsage

from fastapi import WebSocket


from pipecat.frames.frames import (
    Frame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMMessagesFrame,
    LLMTextFrame,
    LLMUpdateSettingsFrame,
)
from pipecat.metrics.metrics import LLMTokenUsage
from pipecat.processors.aggregators.openai_llm_context import (
    OpenAILLMContext,
    OpenAILLMContextFrame,
)
from pipecat.processors.frame_processor import FrameDirection
from pipecat.services.llm_service import LLMService
from pipecat.utils.tracing.service_decorators import traced_llm


class OpenAIUnhandledFunctionException(Exception):
    pass


class BaseOpenAILLMService(LLMService):
    """This is the base for all services that use the AsyncGroq client."""

    class InputParams(BaseModel):
        frequency_penalty: Optional[float] = Field(default=0.0, ge=-2.0, le=2.0)
        presence_penalty: Optional[float] = Field(default=0.0, ge=-2.0, le=2.0)
        seed: Optional[int] = Field(default=None, ge=0)
        temperature: Optional[float] = Field(default=0.7, ge=0.0, le=2.0)
        top_k: Optional[int] = Field(default=None, ge=0)
        top_p: Optional[float] = Field(default=1.0, ge=0.0, le=1.0)
        max_tokens: Optional[int] = Field(default=1024, ge=1)
        max_completion_tokens: Optional[int] = Field(default=None, ge=1)
        extra: Optional[Dict[str, Any]] = Field(default_factory=dict)

    def __init__(
        self,
        *,
        model: str,
        api_key=None,
        base_url=None,
        organization=None,
        project=None,
        default_headers: Optional[Mapping[str, str]] = None,
        params: Optional[InputParams] = None,
        stream: bool = False,
        websocket: WebSocket = None,
        **kwargs,
    ):
        super().__init__(**kwargs)

        params = params or BaseOpenAILLMService.InputParams()

        self._settings = {
            "frequency_penalty": params.frequency_penalty,
            "presence_penalty": params.presence_penalty,
            "seed": params.seed,
            "temperature": params.temperature,
            "top_p": params.top_p,
            "max_tokens": params.max_tokens,
            "max_completion_tokens": params.max_completion_tokens,
            "extra": params.extra if isinstance(params.extra, dict) else {},
        }
        self._stream = stream
        self._websocket = websocket
        self.set_model_name(model)
        self._client = self.create_client(
            api_key=api_key,
            base_url=base_url,
            organization=organization,
            project=project,
            default_headers=default_headers,
            **kwargs,
        )

    def create_client(
        self,
        api_key=None,
        base_url=None,
        organization=None,
        project=None,
        default_headers=None,
        **kwargs,
    ):
        return AsyncGroq(
            api_key=api_key,
            base_url=base_url,
            default_headers=default_headers,
        )

    def can_generate_metrics(self) -> bool:
        return True

    async def send_to_websocket(self, content: str):
        """Send content to the LLM WebSocket"""
        if self.websocket:
            try:
                await self.websocket.send_json({
                    "type": "llm_response",
                    "content": content
                })
            except Exception as e:
                print(f"Failed to send to LLM WebSocket: {e}")


    async def get_chat_completions(
        self, context: OpenAILLMContext, messages: List[Dict[str, Any]]
    ) -> AsyncStream[ChatCompletionChunk]:
        params = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,  # Get complete response
            "temperature": self._settings["temperature"],
            "top_p": self._settings["top_p"],
            "max_tokens": self._settings["max_tokens"],
        }

        params.update(self._settings["extra"])

        # Get complete response
        response = await self._client.chat.completions.create(**params)
        print(f"RESPONSE: {response}")
        if self._stream:
            await self.send_to_websocket(response.choices[0].message.content)
        # Create a simulated stream that matches AsyncStream[ChatCompletionChunk]
        return self._create_simulated_stream(response)

    async def _stream_chat_completions(
        self, context: OpenAILLMContext
    ) -> AsyncStream[ChatCompletionChunk]:
        logger.debug(f"{self}: Generating chat [{context.get_messages_for_logging()}]")
        messages = context.get_messages()
        return await self.get_chat_completions(context, messages)

    def _create_simulated_stream(self, response) -> AsyncStream[ChatCompletionChunk]:
        """Create a simulated stream from the complete response that matches AsyncStream[ChatCompletionChunk]."""
        class SimulatedStream:
            def __init__(self, response):
                self.content = response.choices[0].message.content
                self.current_pos = 0
                self.chunk_size = 10  # Adjust chunk size as needed
                self.usage = CompletionUsage(
                    prompt_tokens=response.usage.prompt_tokens,
                    completion_tokens=response.usage.completion_tokens,
                    total_tokens=response.usage.total_tokens
                ) if response.usage else None

            def __aiter__(self):
                return self

            async def __anext__(self) -> ChatCompletionChunk:
                if self.current_pos >= len(self.content):
                    raise StopAsyncIteration
                
                # Get next chunk
                chunk = self.content[self.current_pos:self.current_pos + self.chunk_size]
                self.current_pos += self.chunk_size
                
                # Create a ChatCompletionChunk-like object
                return ChatCompletionChunk(
                    id=response.id,
                    choices=[{
                        "delta": {"content": chunk},
                        "finish_reason": None if self.current_pos < len(self.content) else "stop",
                        "index": 0
                    }],
                    created=response.created,
                    model=response.model,
                    object="chat.completion.chunk",
                    usage=self.usage if self.current_pos >= len(self.content) else None
                )

        return SimulatedStream(response)
    @traced_llm
    async def _process_context(self, context: OpenAILLMContext):
        functions_list = []
        arguments_list = []
        tool_id_list = []
        func_idx = 0
        function_name = ""
        arguments = ""
        tool_call_id = ""

        await self.start_ttfb_metrics()

        chunk_stream = await self._stream_chat_completions(context)

        async for chunk in chunk_stream:
            if chunk.choices and chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                await self.push_frame(LLMTextFrame(content))

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        context = None
        if isinstance(frame, OpenAILLMContextFrame):
            context: OpenAILLMContext = frame.context
        elif isinstance(frame, LLMMessagesFrame):
            logger.debug(f"FRAME: {frame.messages}")
            context = OpenAILLMContext.from_messages(frame.messages)
        elif isinstance(frame, LLMUpdateSettingsFrame):
            await self._update_settings(frame.settings)
        else:
            await self.push_frame(frame, direction)

        if context:
            try:
                await self.push_frame(LLMFullResponseStartFrame())
                await self.start_processing_metrics()
                await self._process_context(context)
            except httpx.TimeoutException:
                await self._call_event_handler("on_completion_timeout")
            finally:
                await self.stop_processing_metrics()
                await self.push_frame(LLMFullResponseEndFrame())