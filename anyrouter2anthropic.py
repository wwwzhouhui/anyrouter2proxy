"""
AnyRouter2Anthropic - Anthropic 协议代理服务（Node.js SDK 中转模式）

通过 Node.js 代理层使用官方 Anthropic SDK 转发请求，绕过 WAF 检测。

架构:
  客户端 → Python 代理 (9998) → Node.js 代理 (4000) → anyrouter.top
                                      ↑
                               官方 Node.js SDK
                               (正确的 TLS 指纹)

使用方式：
1. 启动 Node.js 代理: cd node-proxy && npm install && npm start
2. 启动 Python 代理: python anyrouter2anthropic.py
3. 配置客户端 base_url 为: http://localhost:9998
"""

import json
import logging
import os
import random
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
NODE_PROXY_URL = os.getenv("NODE_PROXY_URL", "http://127.0.0.1:4000")
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "120"))
DEFAULT_MAX_TOKENS = int(os.getenv("DEFAULT_MAX_TOKENS", "8192"))


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
        account = self.accounts[self._rr_index % len(self.accounts)]
        self._rr_index += 1
        return account


# 全局 HTTP 客户端
http_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    if http_client is None:
        raise RuntimeError("HTTP client not initialized")
    return http_client


def extract_api_keys(request: Request) -> list[str]:
    """从请求头提取 API keys"""
    api_key = request.headers.get("x-api-key", "")
    if not api_key:
        auth_header = request.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            api_key = auth_header[7:]

    if not api_key:
        return []

    keys = [k.strip() for k in api_key.split(",") if k.strip()]
    return keys


def generate_user_id() -> str:
    user_hash = ''.join(random.choices('0123456789abcdef', k=64))
    session_uuid = uuid.uuid4()
    return f"user_{user_hash}_account__session_{session_uuid}"


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


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global http_client
    http_client = httpx.AsyncClient(timeout=HTTP_TIMEOUT)
    logger.info("Started: Node.js SDK proxy mode enabled")
    logger.info("Node.js proxy URL: %s", NODE_PROXY_URL)
    yield
    await http_client.aclose()


app = FastAPI(title="AnyRouter Anthropic Proxy (Node.js SDK Mode)", lifespan=lifespan)


def build_forwarding_headers(api_key: str, original_headers: dict[str, str] = None) -> dict[str, str]:
    """构建转发到 Node.js 代理的请求头，透传客户端所有特殊头（如 Claude Code 头）"""
    # 需要跳过的 hop-by-hop 头和内部头
    SKIP_HEADERS = {
        "host", "content-length", "transfer-encoding", "connection",
        "keep-alive", "upgrade", "proxy-authorization", "proxy-connection",
        "accept-encoding",
    }

    headers = {}

    # 透传客户端的所有头（保留 Claude Code 发送的所有特殊头）
    if original_headers:
        for key, val in original_headers.items():
            if key.lower() not in SKIP_HEADERS:
                headers[key] = val

    # 确保关键字段
    headers["Content-Type"] = "application/json"
    headers["x-api-key"] = api_key

    # 移除 authorization 避免重复认证
    headers.pop("authorization", None)

    return headers


async def stream_response(
    req: dict[str, Any],
    account: Account,
    forwarding_headers: dict[str, str],
) -> AsyncGenerator[str, None]:
    """转发流式请求到 Node.js 代理"""
    client = get_client()

    try:
        async with client.stream(
            "POST",
            f"{NODE_PROXY_URL}/v1/messages",
            headers=forwarding_headers,
            json=req
        ) as resp:
            if resp.status_code != 200:
                error_text = await resp.aread()
                logger.error("[%s] Error %d: %s", account.name, resp.status_code, error_text.decode()[:200])
                yield f"event: error\ndata: {json.dumps({'type': 'error', 'error': {'type': 'api_error', 'message': error_text.decode()}})}\n\n"
                return

            async for line in resp.aiter_lines():
                if line:
                    yield f"{line}\n"
                else:
                    yield "\n"

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
            detail={"type": "error", "error": {"type": "authentication_error", "message": "API key required"}}
        )

    lb = RequestLoadBalancer(api_keys)
    account = lb.select_account()
    if not account:
        raise HTTPException(status_code=401, detail={"type": "error", "error": {"type": "authentication_error", "message": "Invalid API key"}})

    try:
        req = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # 记录完整的客户端请求信息（用于调试 Claude Code 请求特征）
    original_headers = dict(request.headers)
    logger.info("========== 客户端请求详情 ==========")
    logger.info("[请求头] %s", json.dumps(
        {k: v for k, v in original_headers.items() if k.lower() not in ("x-api-key", "authorization")},
        ensure_ascii=False, indent=2
    ))
    logger.info("[请求体(不含messages)] %s", json.dumps(
        {k: v for k, v in req.items() if k != "messages"},
        ensure_ascii=False
    ))
    logger.info("====================================")

    req = ensure_metadata(req)
    req = ensure_max_tokens(req)

    # 构建转发头，透传客户端所有特殊头
    forwarding_headers = build_forwarding_headers(account.api_key, original_headers)

    model = req.get("model", "unknown")
    is_stream = req.get("stream", False)
    logger.info("[%s] %s stream=%s (via Node.js)", account.name, model, is_stream)

    if is_stream:
        return StreamingResponse(
            stream_response(req, account, forwarding_headers),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )
    else:
        client = get_client()
        try:
            resp = await client.post(
                f"{NODE_PROXY_URL}/v1/messages",
                headers=forwarding_headers,
                json=req
            )

            if resp.status_code != 200:
                logger.error("[%s] Error %d: %s", account.name, resp.status_code, resp.text[:200])
                raise HTTPException(status_code=resp.status_code, detail=resp.text)

            return JSONResponse(content=resp.json())

        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Request timeout")
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=str(e))


@app.get("/v1/models")
async def list_models(request: Request):
    """列出可用模型"""
    models = [
        {"id": "claude-opus-4-5-20251101", "name": "Claude Opus 4.5"},
        {"id": "claude-sonnet-4-5-20250929", "name": "Claude Sonnet 4.5"},
        {"id": "claude-sonnet-4-20250514", "name": "Claude Sonnet 4"},
        {"id": "claude-haiku-4-5-20251001", "name": "Claude Haiku 4.5"},
        {"id": "claude-3-7-sonnet-20250219", "name": "Claude 3.7 Sonnet"},
        {"id": "claude-3-5-sonnet-20241022", "name": "Claude 3.5 Sonnet"},
        {"id": "claude-3-5-haiku-20241022", "name": "Claude 3.5 Haiku"},
    ]
    return {"data": models}


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
        "service": "AnyRouter Anthropic Proxy",
        "mode": "node-proxy",
        "node_proxy_url": NODE_PROXY_URL,
        "description": "Forwarding requests to Node.js proxy (using official Anthropic SDK)",
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "9998"))
    host = os.getenv("HOST", "0.0.0.0")

    print(f"""
╔══════════════════════════════════════════════════════════╗
║     AnyRouter Anthropic Proxy (Node.js SDK Mode)         ║
╠══════════════════════════════════════════════════════════╣
║  Python 代理: http://{host}:{port}
║  Node.js 代理: {NODE_PROXY_URL}
╠══════════════════════════════════════════════════════════╣
║  架构:                                                    ║
║    客户端 → Python (9998) → Node.js (4000) → anyrouter   ║
╠══════════════════════════════════════════════════════════╣
║  启动步骤:                                                ║
║    1. cd node-proxy && npm install && npm start          ║
║    2. python anyrouter2anthropic.py                      ║
╠══════════════════════════════════════════════════════════╣
║  管理接口:                                                ║
║    GET /health - 健康检查（含 Node.js 状态）              ║
╚══════════════════════════════════════════════════════════╝
""")

    uvicorn.run(app, host=host, port=port)
