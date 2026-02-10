"""データモデル - OpenAI API互換フォーマット"""
from pydantic import BaseModel, Field
from typing import Optional, List, Union, Literal
import time
import uuid


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str
    name: Optional[str] = None


class ChatCompletionRequest(BaseModel):
    model: str = "gpt-5"
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = None
    stream: Optional[bool] = False
    new_conversation: Optional[bool] = False
    conversation_id: Optional[str] = None


class ChatCompletionChoice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: Optional[str] = "stop"


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex[:12]}")
    object: str = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: List[ChatCompletionChoice]
    usage: Optional[Usage] = None
    conversation_id: Optional[str] = None


class ModelInfo(BaseModel):
    id: str
    object: str = "model"
    created: int = Field(default_factory=lambda: int(time.time()))
    owned_by: str = "internal"


class ModelsResponse(BaseModel):
    object: str = "list"
    data: List[ModelInfo]


class HealthResponse(BaseModel):
    status: str = "healthy"
    edge_connected: bool = False
    session_count: int = 0
