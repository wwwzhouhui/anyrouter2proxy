"""
AnyRouter2Anthropic - Anthropic 协议代理服务（多账号负载均衡版）

将 Anthropic SDK 请求转发到 AnyRouter，添加必要的请求头和元数据。
支持 Cherry Studio、Anthropic SDK 等工具通过此代理调用 anyrouter.top。

特性：
- 多 API Key 负载均衡
- 支持轮询、随机、权重三种策略
- 账号健康检查和自动故障转移
- 从 .env 文件读取配置

使用方式：
1. 配置 .env 文件中的 API_KEYS
2. 启动代理: python anyrouter2anthropic.py
3. 配置客户端 base_url 为: http://localhost:9998
4. 使用任意字符串作为 api_key（代理会自动选择账号）
"""

import json
import logging
import os
import random
import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
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

# 负载均衡配置
LOAD_BALANCE_STRATEGY = os.getenv("LOAD_BALANCE_STRATEGY", "round_robin")
MAX_FAIL_COUNT = int(os.getenv("MAX_FAIL_COUNT", "3"))
FAIL_RESET_SECONDS = float(os.getenv("FAIL_RESET_SECONDS", "60"))

# 公共请求头
BASE_HEADERS: dict[str, str] = {
    "accept": "application/json",
    "content-type": "application/json",
    "Accept-Encoding": "gzip, deflate, br, zstd",
}


class LoadBalanceStrategy(Enum):
    """负载均衡策略"""
    ROUND_ROBIN = "round_robin"
    RANDOM = "random"
    WEIGHTED = "weighted"


@dataclass
class Account:
    """API 账号"""
    api_key: str
    name: str = ""
    weight: int = 1
    enabled: bool = True
    healthy: bool = True
    fail_count: int = 0
    last_fail_time: float = 0
    total_requests: int = 0
    successful_requests: int = 0

    def __post_init__(self):
        if not self.name:
            self.name = f"account_{self.api_key[:8]}..."


@dataclass
class LoadBalancer:
    """负载均衡器"""
    accounts: list[Account] = field(default_factory=list)
    strategy: LoadBalanceStrategy = LoadBalanceStrategy.ROUND_ROBIN
    _rr_index: int = 0
    _lock: Lock = field(default_factory=Lock)
    max_fail_count: int = 3
    fail_reset_seconds: float = 60.0

    def add_account(self, account: Account):
        self.accounts.append(account)
        logger.info("Added account: %s", account.name)

    def get_healthy_accounts(self) -> list[Account]:
        now = time.time()
        healthy = []
        for acc in self.accounts:
            if not acc.enabled:
                continue
            if not acc.healthy and (now - acc.last_fail_time) > self.fail_reset_seconds:
                acc.healthy = True
                acc.fail_count = 0
                logger.info("Account %s recovered", acc.name)
            if acc.healthy:
                healthy.append(acc)
        return healthy

    def select_account(self) -> Account | None:
        healthy = self.get_healthy_accounts()
        if not healthy:
            for acc in self.accounts:
                if acc.enabled:
                    logger.warning("No healthy accounts, forcing use of %s", acc.name)
                    return acc
            return None

        with self._lock:
            if self.strategy == LoadBalanceStrategy.ROUND_ROBIN:
                account = healthy[self._rr_index % len(healthy)]
                self._rr_index += 1
                return account
            elif self.strategy == LoadBalanceStrategy.RANDOM:
                return random.choice(healthy)
            elif self.strategy == LoadBalanceStrategy.WEIGHTED:
                total_weight = sum(acc.weight for acc in healthy)
                if total_weight == 0:
                    return random.choice(healthy)
                r = random.randint(1, total_weight)
                cumulative = 0
                for acc in healthy:
                    cumulative += acc.weight
                    if r <= cumulative:
                        return acc
                return healthy[-1]
        return healthy[0] if healthy else None

    def mark_success(self, account: Account):
        account.total_requests += 1
        account.successful_requests += 1
        if account.fail_count > 0:
            account.fail_count = 0

    def mark_failure(self, account: Account):
        account.total_requests += 1
        account.fail_count += 1
        account.last_fail_time = time.time()
        if account.fail_count >= self.max_fail_count:
            account.healthy = False
            logger.warning("Account %s marked unhealthy", account.name)

    def get_stats(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy.value,
            "total_accounts": len(self.accounts),
            "healthy_accounts": len(self.get_healthy_accounts()),
            "accounts": [
                {
                    "name": acc.name,
                    "enabled": acc.enabled,
                    "healthy": acc.healthy,
                    "fail_count": acc.fail_count,
                    "total_requests": acc.total_requests,
                    "successful_requests": acc.successful_requests,
                    "success_rate": (
                        f"{acc.successful_requests / acc.total_requests * 100:.1f}%"
                        if acc.total_requests > 0 else "N/A"
                    ),
                }
                for acc in self.accounts
            ]
        }


def load_accounts_from_env() -> LoadBalancer:
    """从环境变量加载账号"""
    lb = LoadBalancer()

    # 设置策略
    try:
        lb.strategy = LoadBalanceStrategy(LOAD_BALANCE_STRATEGY)
    except ValueError:
        logger.warning("Unknown strategy '%s', using round_robin", LOAD_BALANCE_STRATEGY)
        lb.strategy = LoadBalanceStrategy.ROUND_ROBIN

    lb.max_fail_count = MAX_FAIL_COUNT
    lb.fail_reset_seconds = FAIL_RESET_SECONDS

    # 从 API_KEYS 环境变量读取（逗号分隔）
    api_keys = os.getenv("API_KEYS", "")
    if api_keys:
        for i, key in enumerate(api_keys.split(","), 1):
            key = key.strip()
            if key:
                lb.add_account(Account(api_key=key, name=f"账号{i}"))

    if not lb.accounts:
        logger.warning("No accounts! Set API_KEYS in .env file")

    return lb


# 全局变量
load_balancer: LoadBalancer | None = None
http_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    if http_client is None:
        raise RuntimeError("HTTP client not initialized")
    return http_client


def get_load_balancer() -> LoadBalancer:
    if load_balancer is None:
        raise RuntimeError("Load balancer not initialized")
    return load_balancer


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global http_client, load_balancer
    load_balancer = load_accounts_from_env()
    http_client = httpx.AsyncClient(timeout=HTTP_TIMEOUT, verify=False)
    logger.info("Started: %d accounts, strategy=%s", len(load_balancer.accounts), load_balancer.strategy.value)
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
    lb = get_load_balancer()
    success = False

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
                lb.mark_failure(account)
                yield f"event: error\ndata: {json.dumps({'type': 'error', 'error': {'type': 'api_error', 'message': error_text.decode()}})}\n\n"
                return

            async for line in resp.aiter_lines():
                yield f"{line}\n" if line else "\n"
            success = True

    except httpx.TimeoutException:
        logger.error("[%s] Timeout", account.name)
        lb.mark_failure(account)
        yield f"event: error\ndata: {json.dumps({'type': 'error', 'error': {'type': 'timeout_error', 'message': 'Request timeout'}})}\n\n"
    except httpx.HTTPError as e:
        logger.error("[%s] HTTP error: %s", account.name, str(e))
        lb.mark_failure(account)
        yield f"event: error\ndata: {json.dumps({'type': 'error', 'error': {'type': 'api_error', 'message': str(e)}})}\n\n"
    finally:
        if success:
            lb.mark_success(account)


@app.post("/v1/messages")
async def messages(request: Request):
    lb = get_load_balancer()
    account = lb.select_account()
    if not account:
        raise HTTPException(status_code=503, detail="No available accounts")

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
                lb.mark_failure(account)
                raise HTTPException(status_code=resp.status_code, detail=resp.text)
            lb.mark_success(account)
            return JSONResponse(content=resp.json())
        except httpx.TimeoutException:
            lb.mark_failure(account)
            raise HTTPException(status_code=504, detail="Request timeout")
        except httpx.HTTPError as e:
            lb.mark_failure(account)
            raise HTTPException(status_code=502, detail=str(e))


@app.get("/v1/models")
async def list_models():
    lb = get_load_balancer()
    account = lb.select_account()
    if not account:
        raise HTTPException(status_code=503, detail="No available accounts")

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
    return {"status": "ok"}


@app.get("/stats")
async def stats():
    return get_load_balancer().get_stats()


@app.get("/")
async def root():
    lb = get_load_balancer()
    return {
        "service": "AnyRouter Anthropic Proxy",
        "upstream": ANYROUTER_BASE_URL,
        "accounts": len(lb.accounts),
        "healthy": len(lb.get_healthy_accounts()),
        "strategy": lb.strategy.value,
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "9998"))
    host = os.getenv("HOST", "0.0.0.0")

    print(f"""
╔══════════════════════════════════════════════════════════╗
║       AnyRouter Anthropic Proxy (Load Balanced)          ║
╠══════════════════════════════════════════════════════════╣
║  代理地址: http://{host}:{port}
║  上游服务: {ANYROUTER_BASE_URL}
╠══════════════════════════════════════════════════════════╣
║  配置方法: 编辑 .env 文件                                  ║
║    API_KEYS=sk-key1,sk-key2,sk-key3                      ║
╠══════════════════════════════════════════════════════════╣
║  管理接口:                                                ║
║    GET /stats  - 查看统计                                 ║
║    GET /health - 健康检查                                 ║
╚══════════════════════════════════════════════════════════╝
""")

    uvicorn.run(app, host=host, port=port)
