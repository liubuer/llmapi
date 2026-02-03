"""
数据模型 - OpenAI API兼容格式
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Union, Literal
from datetime import datetime
import time
import uuid


# ============ 请求模型 ============

class ChatMessage(BaseModel):
    """聊天消息"""
    role: Literal["system", "user", "assistant"] = Field(
        description="消息角色"
    )
    content: str = Field(
        description="消息内容"
    )
    name: Optional[str] = Field(
        default=None,
        description="发送者名称(可选)"
    )


class ChatCompletionRequest(BaseModel):
    """聊天补全请求 - OpenAI兼容格式"""
    model: str = Field(
        default="gpt-5",
        description="模型名称"
    )
    messages: List[ChatMessage] = Field(
        description="消息列表"
    )
    temperature: Optional[float] = Field(
        default=0.7,
        ge=0,
        le=2,
        description="温度参数"
    )
    max_tokens: Optional[int] = Field(
        default=None,
        description="最大生成token数"
    )
    stream: Optional[bool] = Field(
        default=False,
        description="是否流式输出"
    )
    top_p: Optional[float] = Field(
        default=1.0,
        description="Top-p采样"
    )
    n: Optional[int] = Field(
        default=1,
        description="生成数量"
    )
    stop: Optional[Union[str, List[str]]] = Field(
        default=None,
        description="停止序列"
    )
    presence_penalty: Optional[float] = Field(
        default=0,
        description="存在惩罚"
    )
    frequency_penalty: Optional[float] = Field(
        default=0,
        description="频率惩罚"
    )
    user: Optional[str] = Field(
        default=None,
        description="用户标识"
    )
    
    # 扩展字段
    new_conversation: Optional[bool] = Field(
        default=False,
        description="是否开始新对话（清除上下文）"
    )


class CompletionRequest(BaseModel):
    """文本补全请求"""
    model: str = Field(default="gpt-5")
    prompt: Union[str, List[str]] = Field(description="提示文本")
    max_tokens: Optional[int] = Field(default=None)
    temperature: Optional[float] = Field(default=0.7)
    stream: Optional[bool] = Field(default=False)


# ============ 响应模型 ============

class ChatCompletionChoice(BaseModel):
    """聊天补全选项"""
    index: int = Field(default=0)
    message: ChatMessage
    finish_reason: Optional[str] = Field(default="stop")


class Usage(BaseModel):
    """使用量统计"""
    prompt_tokens: int = Field(default=0)
    completion_tokens: int = Field(default=0)
    total_tokens: int = Field(default=0)


class ChatCompletionResponse(BaseModel):
    """聊天补全响应 - OpenAI兼容格式"""
    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex[:12]}")
    object: str = Field(default="chat.completion")
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: List[ChatCompletionChoice]
    usage: Optional[Usage] = None
    system_fingerprint: Optional[str] = Field(default=None)


class ChatCompletionChunk(BaseModel):
    """流式响应块"""
    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex[:12]}")
    object: str = Field(default="chat.completion.chunk")
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: List[dict]


class CompletionChoice(BaseModel):
    """文本补全选项"""
    text: str
    index: int = Field(default=0)
    logprobs: Optional[dict] = None
    finish_reason: Optional[str] = Field(default="stop")


class CompletionResponse(BaseModel):
    """文本补全响应"""
    id: str = Field(default_factory=lambda: f"cmpl-{uuid.uuid4().hex[:12]}")
    object: str = Field(default="text_completion")
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: List[CompletionChoice]
    usage: Optional[Usage] = None


# ============ 模型信息 ============

class ModelInfo(BaseModel):
    """模型信息"""
    id: str
    object: str = Field(default="model")
    created: int = Field(default_factory=lambda: int(time.time()))
    owned_by: str = Field(default="internal")


class ModelsResponse(BaseModel):
    """模型列表响应"""
    object: str = Field(default="list")
    data: List[ModelInfo]


# ============ 错误响应 ============

class ErrorDetail(BaseModel):
    """错误详情"""
    message: str
    type: str
    param: Optional[str] = None
    code: Optional[str] = None


class ErrorResponse(BaseModel):
    """错误响应"""
    error: ErrorDetail


# ============ 健康检查 ============

class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str = Field(default="healthy")
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat()
    )
    browser_sessions: int = Field(default=0)
    available_sessions: int = Field(default=0)


# ============ 会话管理 ============

class SessionInfo(BaseModel):
    """会话信息"""
    session_id: str
    created_at: str
    last_used: str
    is_busy: bool
    message_count: int
