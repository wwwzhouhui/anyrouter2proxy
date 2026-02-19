import httpx
import json
import asyncio

# 配置代理地址（通过 Node.js 代理链：Python 9998 → Node.js 4000 → anyrouter.top）
PROXY_URL = "http://localhost:9998/v1/messages"
PROXY_MODELS_URL = "http://localhost:9998/v1/models"
DUMMY_API_KEY = "sk-xxxxx"

# 测试模型列表
TEST_MODELS = [
    "claude-opus-4-6",
    "claude-sonnet-4-6",
    "claude-sonnet-4-5-20250929",
    "claude-haiku-4-5-20251001",
]


async def test_models():
    print("\n--- 测试获取模型列表 ---")
    headers = {
        "x-api-key": DUMMY_API_KEY,
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.get(PROXY_MODELS_URL, headers=headers)
            if response.status_code == 200:
                result = response.json()
                print("成功！")
                models = result.get("data", [])
                for m in models:
                    print(f"  - {m.get('id', m.get('name', 'unknown'))}")
            else:
                print(f"失败！状态码: {response.status_code}")
                print(f"错误详情: {response.text}")
        except Exception as e:
            print(f"请求发生异常: {e}")


async def test_non_stream(model: str):
    print(f"\n--- 测试非流式响应 ({model}) ---")
    payload = {
        "model": model,
        "max_tokens": 1024,
        "messages": [
            {"role": "user", "content": "你好，请用一句话自我介绍。"}
        ],
        "stream": False
    }

    headers = {
        "x-api-key": DUMMY_API_KEY,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            response = await client.post(PROXY_URL, json=payload, headers=headers)
            if response.status_code == 200:
                result = response.json()
                print(f"[{model}] 成功！")
                for block in result.get("content", []):
                    if block.get("type") == "text":
                        print(f"  回答内容: {block['text'][:200]}")
                    elif block.get("type") == "thinking":
                        print(f"  思考过程: {block.get('thinking', '')[:100]}...")
            else:
                print(f"[{model}] 失败！状态码: {response.status_code}")
                print(f"  错误详情: {response.text[:300]}")
        except Exception as e:
            print(f"[{model}] 请求发生异常: {e}")


async def test_stream(model: str):
    print(f"\n--- 测试流式响应 ({model}) ---")
    payload = {
        "model": model,
        "max_tokens": 1024,
        "messages": [
            {"role": "user", "content": "讲一个简短的笑话。"}
        ],
        "stream": True
    }

    headers = {
        "x-api-key": DUMMY_API_KEY,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            async with client.stream("POST", PROXY_URL, json=payload, headers=headers) as response:
                if response.status_code == 200:
                    print(f"[{model}] 成功！正在接收流式内容:")
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        if line.startswith("data: "):
                            data_str = line[6:]
                            try:
                                data = json.loads(data_str)
                                event_type = data.get("type")
                                if event_type == "content_block_delta":
                                    delta = data.get("delta", {})
                                    if delta.get("type") == "text_delta":
                                        print(delta.get("text", ""), end="", flush=True)
                                elif event_type == "error":
                                    print(f"\n  错误: {data.get('error', {}).get('message', '')}")
                            except json.JSONDecodeError:
                                pass
                    print("\n  流式传输结束。")
                else:
                    print(f"[{model}] 失败！状态码: {response.status_code}")
                    error_content = await response.aread()
                    print(f"  错误详情: {error_content.decode()[:300]}")
        except Exception as e:
            print(f"[{model}] 请求发生异常: {e}")


async def main():
    print("=" * 60)
    print("AnyRouter Anthropic Proxy 多模型测试")
    print(f"测试模型: {', '.join(TEST_MODELS)}")
    print("=" * 60)

    await test_models()

    for model in TEST_MODELS:
        await test_non_stream(model)
        await test_stream(model)


if __name__ == "__main__":
    asyncio.run(main())
