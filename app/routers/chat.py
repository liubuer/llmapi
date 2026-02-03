"""
聊天API路由 - OpenAI兼容接口
"""
import asyncio
import json
import time
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse
from loguru import logger

from ..models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionChoice,
    ChatCompletionChunk,
    ChatMessage,
    CompletionRequest,
    CompletionResponse,
    CompletionChoice,
    Usage,
    ModelsResponse,
    ModelInfo,
    ErrorResponse,
    ErrorDetail,
)
from ..ai_client import get_ai_client, AIClientError
from ..config import get_settings


router = APIRouter(prefix="/v1", tags=["OpenAI Compatible API"])


def estimate_tokens(text: str) -> int:
    """估算token数量（简单估算）"""
    # 简单估算：英文约4字符/token，中文约2字符/token
    # 这里使用一个通用估算
    return len(text) // 3


@router.post("/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    """
    聊天补全接口 - OpenAI兼容
    
    支持：
    - 多轮对话
    - 系统提示
    - 流式输出
    """
    logger.info(f"收到聊天请求: model={request.model}, messages={len(request.messages)}, stream={request.stream}")
    
    try:
        client = await get_ai_client()
        
        if request.stream:
            return EventSourceResponse(
                stream_chat_response(client, request),
                media_type="text/event-stream"
            )
        else:
            # 非流式响应
            response_text = await client.chat(
                messages=request.messages,
                model=request.model,
                new_conversation=request.new_conversation
            )
            
            # 构建响应
            prompt_tokens = sum(estimate_tokens(m.content) for m in request.messages)
            completion_tokens = estimate_tokens(response_text)
            
            return ChatCompletionResponse(
                model=request.model,
                choices=[
                    ChatCompletionChoice(
                        index=0,
                        message=ChatMessage(
                            role="assistant",
                            content=response_text
                        ),
                        finish_reason="stop"
                    )
                ],
                usage=Usage(
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=prompt_tokens + completion_tokens
                )
            )
            
    except AIClientError as e:
        logger.error(f"AI客户端错误: {e}")
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "message": str(e),
                    "type": "ai_client_error",
                    "code": "service_unavailable"
                }
            }
        )
    except Exception as e:
        logger.exception(f"处理请求时发生错误: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "message": f"内部服务器错误: {str(e)}",
                    "type": "internal_error",
                    "code": "internal_error"
                }
            }
        )


async def stream_chat_response(client, request: ChatCompletionRequest) -> AsyncGenerator[str, None]:
    """流式聊天响应生成器"""
    try:
        response_id = f"chatcmpl-{int(time.time())}"
        
        # 获取流式响应
        stream = await client.chat(
            messages=request.messages,
            model=request.model,
            new_conversation=request.new_conversation,
            stream=True
        )
        
        async for chunk_text in stream:
            chunk = {
                "id": response_id,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": request.model,
                "choices": [{
                    "index": 0,
                    "delta": {"content": chunk_text},
                    "finish_reason": None
                }]
            }
            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        
        # 发送结束标记
        final_chunk = {
            "id": response_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": request.model,
            "choices": [{
                "index": 0,
                "delta": {},
                "finish_reason": "stop"
            }]
        }
        yield f"data: {json.dumps(final_chunk, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
        
    except Exception as e:
        logger.error(f"流式响应错误: {e}")
        error_chunk = {
            "error": {
                "message": str(e),
                "type": "stream_error"
            }
        }
        yield f"data: {json.dumps(error_chunk)}\n\n"


@router.post("/completions")
async def completions(request: CompletionRequest):
    """
    文本补全接口
    """
    logger.info(f"收到补全请求: model={request.model}")
    
    try:
        client = await get_ai_client()
        
        # 将prompt转换为消息格式
        prompt = request.prompt if isinstance(request.prompt, str) else request.prompt[0]
        messages = [ChatMessage(role="user", content=prompt)]
        
        response_text = await client.chat(
            messages=messages,
            model=request.model,
            new_conversation=True
        )
        
        prompt_tokens = estimate_tokens(prompt)
        completion_tokens = estimate_tokens(response_text)
        
        return CompletionResponse(
            model=request.model,
            choices=[
                CompletionChoice(
                    text=response_text,
                    index=0,
                    finish_reason="stop"
                )
            ],
            usage=Usage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens
            )
        )
        
    except AIClientError as e:
        logger.error(f"AI客户端错误: {e}")
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.exception(f"处理请求时发生错误: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models")
async def list_models():
    """列出可用模型"""
    return ModelsResponse(
        data=[
            ModelInfo(id="gpt-5", owned_by="internal"),
            ModelInfo(id="gpt-4o", owned_by="internal"),
        ]
    )


@router.get("/models/{model_id}")
async def get_model(model_id: str):
    """获取模型信息"""
    if model_id in ["gpt-5", "gpt-4o"]:
        return ModelInfo(id=model_id, owned_by="internal")
    raise HTTPException(status_code=404, detail="Model not found")
