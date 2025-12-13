"""
AnyRouter2Openai - 将 OpenAI 协议转换为 AnyRouter 的 Anthropic 协议的代理服务
完全透传请求参数，从请求中获取所有配置
"""

import json
import logging
import os
import random
import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# 配置常量
ANYROUTER_BASE_URL = os.getenv("ANYROUTER_BASE_URL", "https://anyrouter.top")
# 强制后端使用非流式请求（解决第三方流式响应不稳定问题）
FORCE_NON_STREAM = os.getenv("FORCE_NON_STREAM", "false").lower() in ("true", "1", "yes")
DEFAULT_MAX_TOKENS = 10240
HTTP_TIMEOUT = 120.0
DEFAULT_SYSTEM_PROMPT = "You are Claude Code, Anthropic's official CLI for Claude."

# 公共请求头
BASE_HEADERS: dict[str, str] = {
    "accept": "application/json",
    "content-type": "application/json",
    "Accept-Encoding": "gzip, deflate, br, zstd",
}

# HTTP 客户端连接池（全局复用）
http_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    """获取 HTTP 客户端"""
    if http_client is None:
        raise RuntimeError("HTTP client not initialized")
    return http_client


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """应用生命周期管理，复用 HTTP 客户端连接池"""
    global http_client
    http_client = httpx.AsyncClient(timeout=HTTP_TIMEOUT, verify=False)
    logger.info("HTTP client initialized, base URL: %s", ANYROUTER_BASE_URL)
    yield
    await http_client.aclose()
    logger.info("HTTP client closed")


app = FastAPI(title="AnyRouter OpenAI Proxy", lifespan=lifespan)


def generate_request_id() -> str:
    """生成 OpenAI 风格的请求 ID"""
    return f"chatcmpl-{uuid.uuid4().hex[:12]}"


def generate_user_id() -> str:
    """生成完整的复合用户 ID"""
    user_hash = ''.join(random.choices('0123456789abcdef', k=64))
    session_uuid = uuid.uuid4()
    return f"user_{user_hash}_account__session_{session_uuid}"


def build_headers(authorization: str) -> dict[str, str]:
    """构建带认证的请求头"""
    return {**BASE_HEADERS, "authorization": authorization}


def convert_message_content(content: str | list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    转换消息内容为 Anthropic 格式
    支持 OpenAI 的字符串格式和多模态数组格式
    """
    if isinstance(content, str):
        return [{"type": "text", "text": content}]

    # 处理多模态内容
    result = []
    for item in content:
        if item.get("type") == "text":
            result.append({"type": "text", "text": item.get("text", "")})
        elif item.get("type") == "image_url":
            # 转换图片 URL 格式
            image_url = item.get("image_url", {})
            url = image_url.get("url", "")
            if url.startswith("data:"):
                # Base64 编码的图片
                media_type, _, base64_data = url.partition(";base64,")
                media_type = media_type.replace("data:", "")
                result.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": base64_data,
                    }
                })
            else:
                # URL 格式的图片
                result.append({
                    "type": "image",
                    "source": {
                        "type": "url",
                        "url": url,
                    }
                })
    return result if result else [{"type": "text", "text": ""}]


def convert_openai_to_anthropic(openai_request: dict[str, Any]) -> dict[str, Any]:
    """将 OpenAI 请求格式转换为 Anthropic 格式"""
    system_messages: list[dict[str, Any]] = [{
        "type": "text",
        "text": DEFAULT_SYSTEM_PROMPT,
        "cache_control": {"type": "ephemeral"},
    }]
    chat_messages: list[dict[str, Any]] = []

    for msg in openai_request.get("messages", []):
        content = msg.get("content", "")
        role = msg.get("role", "")

        if role == "system":
            # 系统消息添加到 system 数组
            if isinstance(content, str):
                system_messages.append({"type": "text", "text": content})
            else:
                # 多模态系统消息
                system_messages.extend(convert_message_content(content))
        elif role in ("user", "assistant"):
            chat_messages.append({
                "role": role,
                "content": convert_message_content(content)
            })
        elif role == "tool":
            # 工具调用结果转换
            chat_messages.append({
                "role": "user",
                "content": convert_message_content(content)
            })

    anthropic_request: dict[str, Any] = {
        "model": openai_request.get("model"),
        "messages": chat_messages,
        "system": system_messages,
        "max_tokens": openai_request.get("max_tokens", DEFAULT_MAX_TOKENS),
        "stream": True,
        "metadata": {"user_id": generate_user_id()},
    }

    # 透传可选参数
    optional_params = {
        "temperature": "temperature",
        "top_p": "top_p",
        "stop": "stop_sequences",
    }
    for openai_key, anthropic_key in optional_params.items():
        if openai_key in openai_request:
            anthropic_request[anthropic_key] = openai_request[openai_key]

    return anthropic_request


def convert_anthropic_response_to_openai(
    anthropic_response: dict[str, Any],
    model: str,
    request_id: str
) -> dict[str, Any]:
    """将 Anthropic 响应转换为 OpenAI 格式"""
    content = "".join(
        block.get("text", "")
        for block in anthropic_response.get("content", [])
        if block.get("type") == "text"
    )

    usage = anthropic_response.get("usage", {})
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)

    # 映射 stop_reason
    stop_reason = anthropic_response.get("stop_reason", "")
    finish_reason = "stop" if stop_reason == "end_turn" else "length"

    return {
        "id": request_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": content},
            "finish_reason": finish_reason,
        }],
        "usage": {
            "prompt_tokens": input_tokens,
            "completion_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
    }


def create_stream_chunk(
    request_id: str,
    model: str,
    content: str | None = None,
    finish_reason: str | None = None
) -> dict[str, Any]:
    """创建流式响应的 chunk"""
    delta: dict[str, Any] = {}
    if content is not None:
        delta["content"] = content

    return {
        "id": request_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "delta": delta,
            "finish_reason": finish_reason,
        }],
    }


async def stream_response(
    anthropic_request: dict[str, Any],
    headers: dict[str, str],
    request_id: str,
    model: str
) -> AsyncGenerator[str, None]:
    """处理流式响应"""
    client = get_client()
    try:
        async with client.stream(
            "POST",
            f"{ANYROUTER_BASE_URL}/v1/messages",
            headers=headers,
            json=anthropic_request
        ) as resp:
            if resp.status_code != 200:
                error_text = await resp.aread()
                error_chunk = {
                    "error": {
                        "message": error_text.decode(),
                        "type": "api_error",
                        "code": resp.status_code
                    }
                }
                logger.error("Upstream error: %d - %s", resp.status_code, error_text.decode()[:200])
                yield f"data: {json.dumps(error_chunk)}\n\n"
                return

            async for line in resp.aiter_lines():
                if not line or not line.strip():
                    continue

                if not line.startswith("data: "):
                    continue

                data = line[6:]
                try:
                    event = json.loads(data)
                    event_type = event.get("type")

                    if event_type == "content_block_delta":
                        delta = event.get("delta", {})
                        if delta.get("type") == "text_delta":
                            text = delta.get("text", "")
                            chunk = create_stream_chunk(request_id, model, content=text)
                            yield f"data: {json.dumps(chunk)}\n\n"

                    elif event_type == "message_stop":
                        chunk = create_stream_chunk(request_id, model, finish_reason="stop")
                        yield f"data: {json.dumps(chunk)}\n\n"
                        yield "data: [DONE]\n\n"

                    elif event_type == "error":
                        error_msg = event.get("error", {}).get("message", "Unknown error")
                        logger.error("Stream error: %s", error_msg)
                        error_chunk = {
                            "error": {
                                "message": error_msg,
                                "type": "stream_error",
                            }
                        }
                        yield f"data: {json.dumps(error_chunk)}\n\n"

                except json.JSONDecodeError as e:
                    logger.warning("Failed to parse SSE data: %s", str(e))
                    continue

    except httpx.TimeoutException:
        logger.error("Request timeout")
        error_chunk = {"error": {"message": "Request timeout", "type": "timeout_error"}}
        yield f"data: {json.dumps(error_chunk)}\n\n"
    except httpx.HTTPError as e:
        logger.error("HTTP error: %s", str(e))
        error_chunk = {"error": {"message": str(e), "type": "http_error"}}
        yield f"data: {json.dumps(error_chunk)}\n\n"


async def stream_from_non_stream(
    anthropic_request: dict[str, Any],
    headers: dict[str, str],
    request_id: str,
    model: str
) -> AsyncGenerator[str, None]:
    """
    调用非流式 API，将响应转换为流式格式输出
    用于：后端禁用流式，但前端仍需要流式响应的场景
    """
    client = get_client()
    try:
        resp = await client.post(
            f"{ANYROUTER_BASE_URL}/v1/messages",
            headers=headers,
            json=anthropic_request
        )

        if resp.status_code != 200:
            error_chunk = {
                "error": {
                    "message": resp.text,
                    "type": "api_error",
                    "code": resp.status_code
                }
            }
            logger.error("Upstream error: %d - %s", resp.status_code, resp.text[:200])
            yield f"data: {json.dumps(error_chunk)}\n\n"
            return

        anthropic_response = resp.json()

        # 提取文本内容
        content = "".join(
            block.get("text", "")
            for block in anthropic_response.get("content", [])
            if block.get("type") == "text"
        )

        # 将完整内容作为一个 chunk 发送
        if content:
            chunk = create_stream_chunk(request_id, model, content=content)
            yield f"data: {json.dumps(chunk)}\n\n"

        # 发送结束标记
        chunk = create_stream_chunk(request_id, model, finish_reason="stop")
        yield f"data: {json.dumps(chunk)}\n\n"
        yield "data: [DONE]\n\n"

    except httpx.TimeoutException:
        logger.error("Request timeout")
        error_chunk = {"error": {"message": "Request timeout", "type": "timeout_error"}}
        yield f"data: {json.dumps(error_chunk)}\n\n"
    except httpx.HTTPError as e:
        logger.error("HTTP error: %s", str(e))
        error_chunk = {"error": {"message": str(e), "type": "http_error"}}
        yield f"data: {json.dumps(error_chunk)}\n\n"


@app.post("/v1/chat/completions", response_model=None)
async def chat_completions(
    request: Request,
    authorization: str = Header(..., description="Bearer token")
):
    """OpenAI 兼容的 chat completions 接口 - 完全透传参数"""
    openai_request = await request.json()
    anthropic_request = convert_openai_to_anthropic(openai_request)
    headers = build_headers(authorization)

    request_id = generate_request_id()
    model = openai_request.get("model", "unknown")
    is_stream = openai_request.get("stream", True)  # OpenAI 默认流式

    # 后端请求模式：如果开启强制非流式，则后端始终非流式
    use_non_stream_backend = FORCE_NON_STREAM or not is_stream
    if use_non_stream_backend:
        anthropic_request['stream'] = False

    logger.info("Request: model=%s, frontend_stream=%s, backend_stream=%s, messages=%d",
                model, is_stream, not use_non_stream_backend, len(openai_request.get("messages", [])))

    if is_stream:
        # 前端需要流式响应
        handler = stream_from_non_stream if use_non_stream_backend else stream_response
        return StreamingResponse(
            handler(anthropic_request, headers, request_id, model),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )
    else:
        client = get_client()
        try:
            resp = await client.post(
                f"{ANYROUTER_BASE_URL}/v1/messages",
                headers=headers,
                json=anthropic_request
            )

            if resp.status_code != 200:
                logger.error("Upstream error: %d - %s", resp.status_code, resp.text[:200])
                raise HTTPException(status_code=resp.status_code, detail=resp.text)

            anthropic_response = resp.json()
            return convert_anthropic_response_to_openai(anthropic_response, model, request_id)

        except httpx.TimeoutException:
            logger.error("Request timeout")
            raise HTTPException(status_code=504, detail="Request timeout")
        except httpx.HTTPError as e:
            logger.error("HTTP error: %s", str(e))
            raise HTTPException(status_code=502, detail=str(e))


@app.get("/v1/models")
async def list_models(
    authorization: str = Header(..., description="Bearer token")
) -> dict[str, Any]:
    """列出可用模型"""
    headers = build_headers(authorization)
    client = get_client()

    try:
        resp = await client.get(f"{ANYROUTER_BASE_URL}/v1/models", headers=headers)
        if resp.status_code != 200:
            logger.error("Failed to fetch models: %d", resp.status_code)
            raise HTTPException(status_code=resp.status_code, detail=resp.text)

        return {"object": "list", "data": resp.json().get("data", [])}

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Request timeout")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/health")
async def health() -> dict[str, str]:
    """健康检查接口"""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=9999)