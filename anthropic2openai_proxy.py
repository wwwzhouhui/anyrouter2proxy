"""
Anthropic 转 OpenAI 协议转换代理服务器

该服务器接收 Anthropic 格式的请求，转换为 OpenAI 格式，
然后转发到 OpenAI 兼容的后端服务。

调用链路：aa.py (Anthropic SDK) --> 本代理 --> https://renderanyrouter2openai.duckcloud.fun/v1

使用方法：
    python anthropic2openai_proxy.py

然后运行 aa.py 进行测试。
"""

import json
import uuid
import time
import asyncio
from typing import AsyncGenerator, List
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
import httpx
import uvicorn

app = FastAPI(title="Anthropic to OpenAI Proxy")

# 配置参数
OPENAI_API_BASE = "https://renderanyrouter2openai.duckcloud.fun/v1"  # OpenAI 后端地址
OPENAI_API_KEY = "sk-111111111111111"  # API 密钥
PROXY_PORT = 8088  # 代理监听端口

# 全局 HTTP 客户端
http_client = httpx.AsyncClient(timeout=120.0)


def convert_anthropic_to_openai(anthropic_request: dict) -> dict:
    """将 Anthropic messages 格式转换为 OpenAI chat completions 格式"""

    messages = []

    # 处理系统消息（如果存在）
    if "system" in anthropic_request:
        messages.append({
            "role": "system",
            "content": anthropic_request["system"]
        })

    # 转换消息列表
    for msg in anthropic_request.get("messages", []):
        role = msg.get("role", "user")
        content = msg.get("content", "")

        # 处理内容块（Anthropic 格式可能是列表）
        if isinstance(content, list):
            text_parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
                elif isinstance(block, str):
                    text_parts.append(block)
            content = "\n".join(text_parts)

        messages.append({
            "role": role,
            "content": content
        })

    # 构建 OpenAI 请求
    openai_request = {
        "model": anthropic_request.get("model", "claude-haiku-4-5-20251001"),
        "messages": messages,
        "stream": anthropic_request.get("stream", False),
    }

    # 可选参数转换
    if "max_tokens" in anthropic_request:
        openai_request["max_tokens"] = anthropic_request["max_tokens"]
    if "temperature" in anthropic_request:
        openai_request["temperature"] = anthropic_request["temperature"]
    if "top_p" in anthropic_request:
        openai_request["top_p"] = anthropic_request["top_p"]
    if "stop_sequences" in anthropic_request:
        openai_request["stop"] = anthropic_request["stop_sequences"]

    return openai_request


def convert_openai_to_anthropic(openai_response: dict, model: str) -> dict:
    """将 OpenAI chat completions 响应转换为 Anthropic messages 格式"""

    choice = openai_response.get("choices", [{}])[0]
    message = choice.get("message", {})

    return {
        "id": f"msg_{uuid.uuid4().hex[:24]}",
        "type": "message",
        "role": "assistant",
        "content": [
            {
                "type": "text",
                "text": message.get("content", "")
            }
        ],
        "model": model,
        "stop_reason": "end_turn" if choice.get("finish_reason") == "stop" else choice.get("finish_reason"),
        "stop_sequence": None,
        "usage": {
            "input_tokens": openai_response.get("usage", {}).get("prompt_tokens", 0),
            "output_tokens": openai_response.get("usage", {}).get("completion_tokens", 0)
        }
    }


async def stream_openai_and_convert(openai_request: dict, model: str) -> AsyncGenerator[bytes, None]:
    """从 OpenAI 后端流式获取数据并转换为 Anthropic 格式"""

    msg_id = f"msg_{uuid.uuid4().hex[:24]}"

    # 发送 message_start 事件
    start_event = {
        "type": "message_start",
        "message": {
            "id": msg_id,
            "type": "message",
            "role": "assistant",
            "content": [],
            "model": model,
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {"input_tokens": 0, "output_tokens": 0}
        }
    }
    yield f"event: message_start\ndata: {json.dumps(start_event)}\n\n".encode()

    # 发送 content_block_start 事件
    block_start = {
        "type": "content_block_start",
        "index": 0,
        "content_block": {"type": "text", "text": ""}
    }
    yield f"event: content_block_start\ndata: {json.dumps(block_start)}\n\n".encode()

    # 向 OpenAI 后端发起请求
    try:
        async with http_client.stream(
            "POST",
            f"{OPENAI_API_BASE}/chat/completions",
            json=openai_request,
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            }
        ) as response:
            # 检查响应状态
            if response.status_code != 200:
                error_text = await response.aread()
                error_event = {
                    "type": "error",
                    "error": {"type": "api_error", "message": error_text.decode()}
                }
                yield f"event: error\ndata: {json.dumps(error_event)}\n\n".encode()
                return

            # 流式处理内容增量
            async for line in response.aiter_lines():
                line = line.strip()

                if not line or not line.startswith("data: "):
                    continue

                data = line[6:]  # 移除 "data: " 前缀

                if data == "[DONE]":
                    break

                try:
                    chunk = json.loads(data)
                    choices = chunk.get("choices", [])
                    if choices:
                        delta = choices[0].get("delta", {})
                        content = delta.get("content", "")

                        # 如果有内容，发送 content_block_delta 事件
                        if content:
                            delta_event = {
                                "type": "content_block_delta",
                                "index": 0,
                                "delta": {"type": "text_delta", "text": content}
                            }
                            yield f"event: content_block_delta\ndata: {json.dumps(delta_event)}\n\n".encode()
                except json.JSONDecodeError:
                    continue

    except Exception as e:
        # 发送错误事件
        error_event = {
            "type": "error",
            "error": {"type": "api_error", "message": str(e)}
        }
        yield f"event: error\ndata: {json.dumps(error_event)}\n\n".encode()
        return

    # 发送 content_block_stop 事件
    block_stop = {"type": "content_block_stop", "index": 0}
    yield f"event: content_block_stop\ndata: {json.dumps(block_stop)}\n\n".encode()

    # 发送 message_delta 事件（停止原因）
    msg_delta = {
        "type": "message_delta",
        "delta": {"stop_reason": "end_turn", "stop_sequence": None},
        "usage": {"output_tokens": 0}
    }
    yield f"event: message_delta\ndata: {json.dumps(msg_delta)}\n\n".encode()

    # 发送 message_stop 事件
    yield f"event: message_stop\ndata: {json.dumps({'type': 'message_stop'})}\n\n".encode()


@app.post("/v1/messages")
async def anthropic_messages(request: Request):
    """处理 Anthropic messages API 请求并转换为 OpenAI 格式"""

    try:
        # 解析 Anthropic 请求
        anthropic_request = await request.json()
        model = anthropic_request.get("model", "claude-haiku-4-5-20251001")
        is_stream = anthropic_request.get("stream", False)

        # 转换为 OpenAI 格式
        openai_request = convert_anthropic_to_openai(anthropic_request)

        if is_stream:
            # 流式响应
            return StreamingResponse(
                stream_openai_and_convert(openai_request, model),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                }
            )
        else:
            # 非流式响应
            response = await http_client.post(
                f"{OPENAI_API_BASE}/chat/completions",
                json=openai_request,
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json"
                }
            )

            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=response.text)

            openai_response = response.json()
            anthropic_response = convert_openai_to_anthropic(openai_response, model)

            return JSONResponse(content=anthropic_response)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    """健康检查端点"""
    return {"status": "healthy", "service": "anthropic2openai-proxy"}


@app.get("/v1/models")
async def list_models():
    """列出可用模型"""
    return {
        "data": [
            {"id": "claude-haiku-4-5-20251001", "object": "model"},
            {"id": "claude-3-5-haiku-20241022", "object": "model"},
            {"id": "claude-3-5-sonnet-20241022", "object": "model"},
            {"id": "claude-3-7-sonnet-20250219", "object": "model"},
            {"id": "claude-opus-4-5-20251101", "object": "model"},
            {"id": "claude-sonnet-4-20250514", "object": "model"},
            {"id": "claude-sonnet-4-5-20250929", "object": "model"},
        ]
    }


@app.on_event("shutdown")
async def shutdown_event():
    """关闭时清理资源"""
    await http_client.aclose()


if __name__ == "__main__":
    print(f"""
╔═══════════════════════════════════════════════════════════════════╗
║           Anthropic 转 OpenAI 协议转换代理服务器                  ║
╠═══════════════════════════════════════════════════════════════════╣
║  监听地址: http://0.0.0.0:{PROXY_PORT}                                  ║
║  后端服务: {OPENAI_API_BASE}            ║
╠═══════════════════════════════════════════════════════════════════╣
║  调用链路:                                                        ║
║    aa.py (Anthropic SDK)                                          ║
║        ↓                                                          ║
║    本代理服务 (协议转换: Anthropic -> OpenAI)                     ║
║        ↓                                                          ║
║    {OPENAI_API_BASE} (OpenAI 后端)         ║
╠═══════════════════════════════════════════════════════════════════╣
║  API 端点:                                                        ║
║    POST /v1/messages  - Anthropic 消息接口                        ║
║    GET  /health       - 健康检查                                  ║
║    GET  /v1/models    - 模型列表                                  ║
╚═══════════════════════════════════════════════════════════════════╝
""")
    uvicorn.run(app, host="0.0.0.0", port=PROXY_PORT)
