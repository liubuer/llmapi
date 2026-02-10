"""チャットAPIルーター"""
import json
import time
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse
from loguru import logger

from ..models import (
    ChatCompletionRequest, ChatCompletionResponse, ChatCompletionChoice,
    ChatMessage, Usage, ModelsResponse, ModelInfo
)
from ..ai_client import get_ai_client, AIClientError


router = APIRouter(prefix="/v1", tags=["OpenAI API"])


def estimate_tokens(text: str) -> int:
    return len(text) // 3


@router.post("/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    logger.info(f"リクエスト: model={request.model}, messages={len(request.messages)}, "
                f"conversation_id={request.conversation_id}, new_conversation={request.new_conversation}")

    try:
        client = await get_ai_client()

        if request.stream:
            return EventSourceResponse(
                stream_response(client, request),
                media_type="text/event-stream"
            )

        response_text, conversation_id = await client.chat(
            messages=request.messages,
            model=request.model,
            stream=False,
            conversation_id=request.conversation_id,
            new_conversation=request.new_conversation
        )

        return ChatCompletionResponse(
            model=request.model,
            choices=[ChatCompletionChoice(
                message=ChatMessage(role="assistant", content=response_text)
            )],
            usage=Usage(
                prompt_tokens=sum(estimate_tokens(m.content) for m in request.messages),
                completion_tokens=estimate_tokens(response_text),
                total_tokens=0
            ),
            conversation_id=conversation_id
        )

    except AIClientError as e:
        logger.error(f"AIクライアントエラー: {e}")
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.exception(f"エラー: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def stream_response(client, request) -> AsyncGenerator[dict, None]:
    try:
        response_id = f"chatcmpl-{int(time.time())}"
        result = await client.chat(
            messages=request.messages,
            model=request.model,
            stream=True,
            conversation_id=request.conversation_id,
            new_conversation=request.new_conversation
        )
        stream, conversation_id = result

        # Send conversation_id as the first event
        conv_data = {
            "id": response_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": request.model,
            "conversation_id": conversation_id,
            "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]
        }
        yield {"data": json.dumps(conv_data, ensure_ascii=False)}

        async for chunk in stream:
            if chunk:  # Only yield non-empty chunks
                data = {
                    "id": response_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": request.model,
                    "conversation_id": conversation_id,
                    "choices": [{"index": 0, "delta": {"content": chunk}, "finish_reason": None}]
                }
                yield {"data": json.dumps(data, ensure_ascii=False)}

        final = {
            "id": response_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": request.model,
            "conversation_id": conversation_id,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]
        }
        yield {"data": json.dumps(final, ensure_ascii=False)}
        yield {"data": "[DONE]"}

    except Exception as e:
        logger.error(f"ストリーミングエラー: {e}")
        error_data = {
            "id": f"chatcmpl-{int(time.time())}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": request.model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]
        }
        yield {"data": json.dumps(error_data, ensure_ascii=False)}
        yield {"data": "[DONE]"}


@router.get("/models")
async def list_models():
    return ModelsResponse(data=[
        ModelInfo(id="gpt-5"),
        ModelInfo(id="gpt-4o"),
    ])


@router.get("/conversations")
async def list_conversations():
    """アクティブな会話を一覧表示"""
    from ..edge_manager import edge_manager
    conversations = edge_manager.list_conversations()
    return {"conversations": conversations}


@router.delete("/conversations/{conversation_id}")
async def remove_conversation(conversation_id: str):
    """会話を削除"""
    from ..edge_manager import edge_manager
    removed = edge_manager.remove_conversation(conversation_id)
    if removed:
        return {"status": "removed", "conversation_id": conversation_id}
    raise HTTPException(status_code=404, detail=f"会話 {conversation_id} が存在しません")


@router.get("/debug/selectors")
async def debug_selectors():
    """デバッグエンドポイント：ページ上のセレクターマッチング状況を確認"""
    from ..edge_manager import edge_manager
    from ..config import get_settings

    settings = get_settings()

    if not edge_manager.is_connected:
        return {"error": "Edge未接続", "connected": False}

    try:
        async with edge_manager.acquire_session() as session:
            page = session.page

            # 現在のページ情報を取得
            url = page.url
            title = await page.title()

            # 各セレクターを確認
            results = {
                "url": url,
                "title": title,
                "selectors": {}
            }

            # 入力ボックスを確認
            input_selectors = settings.selector_input.split(",")
            for sel in input_selectors:
                sel = sel.strip()
                try:
                    count = await page.locator(sel).count()
                    results["selectors"][f"input: {sel}"] = count
                except Exception as e:
                    results["selectors"][f"input: {sel}"] = f"エラー: {e}"

            # レスポンスセレクターを確認
            response_selectors = settings.selector_response.split(",")
            for sel in response_selectors:
                sel = sel.strip()
                try:
                    locator = page.locator(sel)
                    count = await locator.count()
                    texts = []
                    for i in range(min(count, 3)):  # 最大3件表示
                        try:
                            text = await locator.nth(i).inner_text()
                            texts.append(text[:100] + "..." if len(text) > 100 else text)
                        except:
                            pass
                    results["selectors"][f"response: {sel}"] = {"count": count, "samples": texts}
                except Exception as e:
                    results["selectors"][f"response: {sel}"] = f"エラー: {e}"

            # 読み込みセレクターを確認
            try:
                count = await page.locator(settings.selector_loading).count()
                results["selectors"]["loading"] = count
            except Exception as e:
                results["selectors"]["loading"] = f"エラー: {e}"

            return results

    except Exception as e:
        return {"error": str(e)}
