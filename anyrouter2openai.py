"""
AnyRouter2OpenAI - OpenAI 协议代理服务（Node.js SDK 中转模式）

将 OpenAI 协议转换为 Anthropic 协议，通过 Node.js 代理层转发请求。
支持多 API Key 负载均衡（客户端提供）。

架构:
  客户端 → Python 代理 (9999) → Node.js 代理 (4000) → anyrouter.top
                                      ↑
                               官方 Node.js SDK
                               (正确的 TLS 指纹)

使用方式：
1. 启动 Node.js 代理: cd node-proxy && npm install && npm start
2. 启动 Python 代理: python anyrouter2openai.py
3. 配置客户端 base_url 为: http://localhost:9999
4. 支持多 key 负载均衡: 用逗号分隔多个 key，如 "sk-key1,sk-key2"
"""

import json
import logging
import os
import random
import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

# 加载 .env 文件
load_dotenv()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# 从环境变量读取配置
NODE_PROXY_URL = os.getenv("NODE_PROXY_URL", "http://127.0.0.1:4000")
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "120"))
DEFAULT_MAX_TOKENS = int(os.getenv("DEFAULT_MAX_TOKENS", "8192"))
FORCE_NON_STREAM = os.getenv("FORCE_NON_STREAM", "false").lower() in ("true", "1", "yes")
DEFAULT_SYSTEM_PROMPT = os.getenv("DEFAULT_SYSTEM_PROMPT", "You are Claude, a helpful AI assistant.")


@dataclass
class Account:
    """API 账号"""
    api_key: str
    name: str = ""

    def __post_init__(self):
        if not self.name:
            self.name = f"key_{self.api_key[:8]}..."


class RequestLoadBalancer:
    """请求级负载均衡器（基于客户端提供的 keys）"""

    def __init__(self, api_keys: list[str]):
        self.accounts = [Account(api_key=k, name=f"key_{i+1}") for i, k in enumerate(api_keys)]
        self._rr_index = 0

    def select_account(self) -> Account | None:
        if not self.accounts:
            return None
        if len(self.accounts) == 1:
            return self.accounts[0]
        # 轮询策略
        account = self.accounts[self._rr_index % len(self.accounts)]
        self._rr_index += 1
        return account


# 全局变量
http_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    if http_client is None:
        raise RuntimeError("HTTP client not initialized")
    return http_client


def extract_api_keys(request: Request) -> list[str]:
    """从请求头提取 API keys（支持逗号分隔的多个 key）"""
    auth_header = request.headers.get("authorization", "")
    if not auth_header:
        return []

    # 移除 Bearer 前缀
    if auth_header.lower().startswith("bearer "):
        auth_header = auth_header[7:]

    # 支持逗号分隔的多个 key
    keys = [k.strip() for k in auth_header.split(",") if k.strip()]
    return keys


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global http_client
    http_client = httpx.AsyncClient(timeout=HTTP_TIMEOUT)
    logger.info("Started: Node.js SDK proxy mode enabled")
    logger.info("Node.js proxy URL: %s", NODE_PROXY_URL)
    yield
    await http_client.aclose()


app = FastAPI(title="AnyRouter OpenAI Proxy (Node.js SDK Mode)", lifespan=lifespan)


def generate_request_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex[:12]}"


def generate_user_id() -> str:
    user_hash = ''.join(random.choices('0123456789abcdef', k=64))
    session_uuid = uuid.uuid4()
    return f"user_{user_hash}_account__session_{session_uuid}"


def build_headers(api_key: str) -> dict[str, str]:
    """构建请求头（简化版，复杂头部由 Node.js 代理处理）"""
    return {
        "Content-Type": "application/json",
        "x-api-key": api_key,
    }


def convert_message_content(content: str | list[dict[str, Any]]) -> list[dict[str, Any]]:
    """转换消息内容为 Anthropic 格式"""
    if isinstance(content, str):
        return [{"type": "text", "text": content}]

    result = []
    for item in content:
        if item.get("type") == "text":
            result.append({"type": "text", "text": item.get("text", "")})
        elif item.get("type") == "image_url":
            image_url = item.get("image_url", {})
            url = image_url.get("url", "")
            if url.startswith("data:"):
                media_type, _, base64_data = url.partition(";base64,")
                media_type = media_type.replace("data:", "")
                result.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": base64_data}
                })
            else:
                result.append({"type": "image", "source": {"type": "url", "url": url}})
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
            if isinstance(content, str):
                system_messages.append({"type": "text", "text": content})
            else:
                system_messages.extend(convert_message_content(content))
        elif role in ("user", "assistant"):
            chat_messages.append({"role": role, "content": convert_message_content(content)})
        elif role == "tool":
            chat_messages.append({"role": "user", "content": convert_message_content(content)})

    anthropic_request: dict[str, Any] = {
        "model": openai_request.get("model"),
        "messages": chat_messages,
        "system": system_messages,
        "max_tokens": openai_request.get("max_tokens", DEFAULT_MAX_TOKENS),
        "stream": True,
        "metadata": {"user_id": generate_user_id()},
    }

    optional_params = {"temperature": "temperature", "top_p": "top_p", "stop": "stop_sequences"}
    for openai_key, anthropic_key in optional_params.items():
        if openai_key in openai_request:
            anthropic_request[anthropic_key] = openai_request[openai_key]

    return anthropic_request


def convert_anthropic_response_to_openai(
    anthropic_response: dict[str, Any], model: str, request_id: str
) -> dict[str, Any]:
    """将 Anthropic 响应转换为 OpenAI 格式"""
    content = "".join(
        block.get("text", "") for block in anthropic_response.get("content", [])
        if block.get("type") == "text"
    )
    usage = anthropic_response.get("usage", {})
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    stop_reason = anthropic_response.get("stop_reason", "")
    finish_reason = "stop" if stop_reason == "end_turn" else "length"

    return {
        "id": request_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": input_tokens, "completion_tokens": output_tokens, "total_tokens": input_tokens + output_tokens},
    }


def create_stream_chunk(request_id: str, model: str, content: str | None = None, finish_reason: str | None = None) -> dict[str, Any]:
    delta: dict[str, Any] = {}
    if content is not None:
        delta["content"] = content
    return {
        "id": request_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }


async def stream_response(
    anthropic_request: dict[str, Any],
    account: Account,
    headers: dict[str, str],
    request_id: str,
    model: str
) -> AsyncGenerator[str, None]:
    """处理流式响应"""
    client = get_client()

    try:
        async with client.stream(
            "POST", f"{NODE_PROXY_URL}/v1/messages", headers=headers, json=anthropic_request
        ) as resp:
            if resp.status_code != 200:
                error_text = await resp.aread()
                logger.error("[%s] Error %d: %s", account.name, resp.status_code, error_text.decode()[:200])
                yield f"data: {json.dumps({'error': {'message': error_text.decode(), 'type': 'api_error', 'code': resp.status_code}})}\n\n"
                return

            async for line in resp.aiter_lines():
                if not line or not line.strip() or not line.startswith("data: "):
                    continue

                try:
                    event = json.loads(line[6:])
                    event_type = event.get("type")

                    if event_type == "content_block_delta":
                        delta = event.get("delta", {})
                        if delta.get("type") == "text_delta":
                            chunk = create_stream_chunk(request_id, model, content=delta.get("text", ""))
                            yield f"data: {json.dumps(chunk)}\n\n"
                    elif event_type == "message_stop":
                        chunk = create_stream_chunk(request_id, model, finish_reason="stop")
                        yield f"data: {json.dumps(chunk)}\n\n"
                        yield "data: [DONE]\n\n"
                    elif event_type == "error":
                        error_msg = event.get("error", {}).get("message", "Unknown error")
                        logger.error("[%s] Stream error: %s", account.name, error_msg)
                        yield f"data: {json.dumps({'error': {'message': error_msg, 'type': 'stream_error'}})}\n\n"
                except json.JSONDecodeError:
                    continue

    except httpx.TimeoutException:
        logger.error("[%s] Timeout", account.name)
        yield f"data: {json.dumps({'error': {'message': 'Request timeout', 'type': 'timeout_error'}})}\n\n"
    except httpx.HTTPError as e:
        logger.error("[%s] HTTP error: %s", account.name, str(e))
        yield f"data: {json.dumps({'error': {'message': str(e), 'type': 'http_error'}})}\n\n"


async def stream_from_non_stream(
    anthropic_request: dict[str, Any],
    account: Account,
    headers: dict[str, str],
    request_id: str,
    model: str
) -> AsyncGenerator[str, None]:
    """非流式后端 + 流式前端"""
    client = get_client()

    try:
        resp = await client.post(f"{NODE_PROXY_URL}/v1/messages", headers=headers, json=anthropic_request)

        if resp.status_code != 200:
            logger.error("[%s] Error %d: %s", account.name, resp.status_code, resp.text[:200])
            yield f"data: {json.dumps({'error': {'message': resp.text, 'type': 'api_error', 'code': resp.status_code}})}\n\n"
            return

        anthropic_response = resp.json()
        content = "".join(
            block.get("text", "") for block in anthropic_response.get("content", [])
            if block.get("type") == "text"
        )

        if content:
            yield f"data: {json.dumps(create_stream_chunk(request_id, model, content=content))}\n\n"

        yield f"data: {json.dumps(create_stream_chunk(request_id, model, finish_reason='stop'))}\n\n"
        yield "data: [DONE]\n\n"

    except httpx.TimeoutException:
        logger.error("[%s] Timeout", account.name)
        yield f"data: {json.dumps({'error': {'message': 'Request timeout', 'type': 'timeout_error'}})}\n\n"
    except httpx.HTTPError as e:
        logger.error("[%s] HTTP error: %s", account.name, str(e))
        yield f"data: {json.dumps({'error': {'message': str(e), 'type': 'http_error'}})}\n\n"


@app.post("/v1/chat/completions", response_model=None)
async def chat_completions(request: Request):
    """OpenAI 兼容的 chat completions 接口"""
    # 提取并验证 API keys
    api_keys = extract_api_keys(request)
    if not api_keys:
        raise HTTPException(
            status_code=401,
            detail={"error": {"message": "Authorization header required. Please provide a valid API key.", "type": "authentication_error"}}
        )

    # 创建请求级负载均衡器
    lb = RequestLoadBalancer(api_keys)
    account = lb.select_account()
    if not account:
        raise HTTPException(status_code=401, detail={"error": {"message": "Invalid API key", "type": "authentication_error"}})

    openai_request = await request.json()
    anthropic_request = convert_openai_to_anthropic(openai_request)
    headers = build_headers(account.api_key)

    request_id = generate_request_id()
    model = openai_request.get("model", "unknown")
    is_stream = openai_request.get("stream", True)

    use_non_stream_backend = FORCE_NON_STREAM or not is_stream
    if use_non_stream_backend:
        anthropic_request['stream'] = False

    logger.info("[%s] %s stream=%s backend_stream=%s", account.name, model, is_stream, not use_non_stream_backend)

    if is_stream:
        handler = stream_from_non_stream if use_non_stream_backend else stream_response
        return StreamingResponse(
            handler(anthropic_request, account, headers, request_id, model),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )
    else:
        client = get_client()
        try:
            resp = await client.post(f"{NODE_PROXY_URL}/v1/messages", headers=headers, json=anthropic_request)
            if resp.status_code != 200:
                logger.error("[%s] Error %d", account.name, resp.status_code)
                raise HTTPException(status_code=resp.status_code, detail=resp.text)
            return convert_anthropic_response_to_openai(resp.json(), model, request_id)
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Request timeout")
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=str(e))


@app.get("/v1/models")
async def list_models(request: Request):
    """列出可用模型"""
    api_keys = extract_api_keys(request)
    if not api_keys:
        raise HTTPException(
            status_code=401,
            detail={"error": {"message": "Authorization header required", "type": "authentication_error"}}
        )

    lb = RequestLoadBalancer(api_keys)
    account = lb.select_account()
    if not account:
        raise HTTPException(status_code=401, detail={"error": {"message": "Invalid API key", "type": "authentication_error"}})

    headers = build_headers(account.api_key)
    client = get_client()
    try:
        resp = await client.get(f"{NODE_PROXY_URL}/v1/models", headers=headers)
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        return {"object": "list", "data": resp.json().get("data", [])}
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Request timeout")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/health")
async def health():
    # 检查 Node.js 代理是否可用
    try:
        client = get_client()
        resp = await client.get(f"{NODE_PROXY_URL}/health", timeout=5)
        node_status = resp.json() if resp.status_code == 200 else {"status": "error"}
    except Exception:
        node_status = {"status": "unreachable"}

    return {
        "status": "ok",
        "mode": "node-proxy",
        "node_proxy": NODE_PROXY_URL,
        "node_status": node_status,
    }


@app.get("/")
async def root():
    return {
        "service": "AnyRouter OpenAI Proxy",
        "mode": "node-proxy",
        "node_proxy_url": NODE_PROXY_URL,
        "description": "Forwarding requests to Node.js proxy (using official Anthropic SDK)",
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("OPENAI_PROXY_PORT", "9999"))
    host = os.getenv("HOST", "0.0.0.0")

    print(f"""
╔══════════════════════════════════════════════════════════╗
║       AnyRouter OpenAI Proxy (Node.js SDK Mode)          ║
╠══════════════════════════════════════════════════════════╣
║  Python 代理: http://{host}:{port}
║  Node.js 代理: {NODE_PROXY_URL}
╠══════════════════════════════════════════════════════════╣
║  架构:                                                    ║
║    客户端 → Python (9999) → Node.js (4000) → anyrouter   ║
╠══════════════════════════════════════════════════════════╣
║  启动步骤:                                                ║
║    1. cd node-proxy && npm install && npm start          ║
║    2. python anyrouter2openai.py                         ║
╠══════════════════════════════════════════════════════════╣
║  管理接口:                                                ║
║    GET /health - 健康检查（含 Node.js 状态）              ║
╚══════════════════════════════════════════════════════════╝
""")

    uvicorn.run(app, host=host, port=port)
