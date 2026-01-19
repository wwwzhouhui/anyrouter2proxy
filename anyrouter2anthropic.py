"""
AnyRouter2Anthropic - Anthropic 协议代理服务（透传模式）

将 Anthropic SDK 请求转发到 AnyRouter，添加必要的请求头和元数据。
支持 Cherry Studio、Anthropic SDK 等工具通过此代理调用 anyrouter.top。

特性：
- 透传模式：客户端必须提供有效的 API Key
- 支持多 key 负载均衡（逗号分隔）

使用方式：
1. 启动代理: python anyrouter2anthropic.py
2. 配置客户端 base_url 为: http://localhost:9998
3. 客户端必须提供有效的 anyrouter.top API key
4. 支持多 key: 用逗号分隔多个 key，如 "sk-key1,sk-key2"
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
from fastapi.responses import StreamingResponse, JSONResponse

# 加载 .env 文件
load_dotenv()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# 从环境变量读取配置
ANYROUTER_BASE_URL = os.getenv("ANYROUTER_BASE_URL", "https://anyrouter.top")
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "120"))
DEFAULT_MAX_TOKENS = int(os.getenv("DEFAULT_MAX_TOKENS", "8192"))

# 公共请求头
BASE_HEADERS: dict[str, str] = {
    "accept": "application/json",
    "content-type": "application/json",
    "Accept-Encoding": "gzip, deflate, br, zstd",
}


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
    # 优先从 x-api-key header 获取（Anthropic SDK 风格）
    api_key = request.headers.get("x-api-key", "")
    if not api_key:
        # 回退到 Authorization header（Bearer token 风格）
        auth_header = request.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            api_key = auth_header[7:]

    if not api_key:
        return []

    # 支持逗号分隔的多个 key
    keys = [k.strip() for k in api_key.split(",") if k.strip()]
    return keys


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global http_client
    http_client = httpx.AsyncClient(timeout=HTTP_TIMEOUT, verify=False)
    logger.info("Started: Passthrough mode enabled")
    yield
    await http_client.aclose()


app = FastAPI(title="AnyRouter Anthropic Proxy", lifespan=lifespan)


def generate_user_id() -> str:
    user_hash = ''.join(random.choices('0123456789abcdef', k=64))
    session_uuid = uuid.uuid4()
    return f"user_{user_hash}_account__session_{session_uuid}"


def build_headers(api_key: str) -> dict[str, str]:
    headers = BASE_HEADERS.copy()
    if api_key.startswith("Bearer "):
        headers["authorization"] = api_key
    else:
        headers["authorization"] = f"Bearer {api_key}"
    return headers


def ensure_metadata(req: dict[str, Any]) -> dict[str, Any]:
    if "metadata" not in req:
        req["metadata"] = {}
    if "user_id" not in req["metadata"]:
        req["metadata"]["user_id"] = generate_user_id()
    return req


def ensure_max_tokens(req: dict[str, Any]) -> dict[str, Any]:
    if "max_tokens" not in req:
        req["max_tokens"] = DEFAULT_MAX_TOKENS
    return req


async def stream_response(
    req: dict[str, Any],
    account: Account,
    headers: dict[str, str]
) -> AsyncGenerator[str, None]:
    client = get_client()

    try:
        async with client.stream(
            "POST",
            f"{ANYROUTER_BASE_URL}/v1/messages",
            headers=headers,
            json=req
        ) as resp:
            if resp.status_code != 200:
                error_text = await resp.aread()
                logger.error("[%s] Error %d: %s", account.name, resp.status_code, error_text.decode()[:200])
                yield f"event: error\ndata: {json.dumps({'type': 'error', 'error': {'type': 'api_error', 'message': error_text.decode()}})}\n\n"
                return

            async for line in resp.aiter_lines():
                yield f"{line}\n" if line else "\n"

    except httpx.TimeoutException:
        logger.error("[%s] Timeout", account.name)
        yield f"event: error\ndata: {json.dumps({'type': 'error', 'error': {'type': 'timeout_error', 'message': 'Request timeout'}})}\n\n"
    except httpx.HTTPError as e:
        logger.error("[%s] HTTP error: %s", account.name, str(e))
        yield f"event: error\ndata: {json.dumps({'type': 'error', 'error': {'type': 'api_error', 'message': str(e)}})}\n\n"


@app.post("/v1/messages")
async def messages(request: Request):
    # 提取并验证 API keys
    api_keys = extract_api_keys(request)
    if not api_keys:
        raise HTTPException(
            status_code=401,
            detail={"type": "error", "error": {"type": "authentication_error", "message": "API key required. Please provide x-api-key header or Authorization: Bearer <key>"}}
        )

    # 创建请求级负载均衡器
    lb = RequestLoadBalancer(api_keys)
    account = lb.select_account()
    if not account:
        raise HTTPException(status_code=401, detail={"type": "error", "error": {"type": "authentication_error", "message": "Invalid API key"}})

    try:
        req = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    req = ensure_metadata(req)
    req = ensure_max_tokens(req)
    headers = build_headers(account.api_key)

    model = req.get("model", "unknown")
    is_stream = req.get("stream", False)
    logger.info("[%s] %s stream=%s", account.name, model, is_stream)

    if is_stream:
        return StreamingResponse(
            stream_response(req, account, headers),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )
    else:
        client = get_client()
        try:
            resp = await client.post(f"{ANYROUTER_BASE_URL}/v1/messages", headers=headers, json=req)
            if resp.status_code != 200:
                logger.error("[%s] Error %d", account.name, resp.status_code)
                raise HTTPException(status_code=resp.status_code, detail=resp.text)
            return JSONResponse(content=resp.json())
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Request timeout")
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=str(e))


@app.get("/v1/models")
async def list_models(request: Request):
    api_keys = extract_api_keys(request)
    if not api_keys:
        raise HTTPException(
            status_code=401,
            detail={"type": "error", "error": {"type": "authentication_error", "message": "API key required"}}
        )

    lb = RequestLoadBalancer(api_keys)
    account = lb.select_account()
    if not account:
        raise HTTPException(status_code=401, detail={"type": "error", "error": {"type": "authentication_error", "message": "Invalid API key"}})

    headers = build_headers(account.api_key)
    client = get_client()
    try:
        resp = await client.get(f"{ANYROUTER_BASE_URL}/v1/models", headers=headers)
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        return resp.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Request timeout")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/health")
async def health():
    return {"status": "ok", "mode": "passthrough"}


@app.get("/")
async def root():
    return {
        "service": "AnyRouter Anthropic Proxy",
        "mode": "passthrough",
        "upstream": ANYROUTER_BASE_URL,
        "description": "Client must provide valid API key(s) via x-api-key header or Authorization: Bearer",
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "9998"))
    host = os.getenv("HOST", "0.0.0.0")

    print(f"""
╔══════════════════════════════════════════════════════════╗
║       AnyRouter Anthropic Proxy (Passthrough Mode)       ║
╠══════════════════════════════════════════════════════════╣
║  代理地址: http://{host}:{port}
║  上游服务: {ANYROUTER_BASE_URL}
╠══════════════════════════════════════════════════════════╣
║  透传模式: 客户端必须提供有效的 API Key                    ║
║  负载均衡: 支持多 key (逗号分隔)                          ║
╠══════════════════════════════════════════════════════════╣
║  客户端配置示例:                                          ║
║    x-api-key: sk-your-key                                ║
║    或 Authorization: Bearer sk-key1,sk-key2              ║
╠══════════════════════════════════════════════════════════╣
║  管理接口:                                                ║
║    GET /health - 健康检查                                 ║
╚══════════════════════════════════════════════════════════╝
""")

    uvicorn.run(app, host=host, port=port)
