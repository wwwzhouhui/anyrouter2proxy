import httpx
import json
import asyncio

# 配置代理地址（请确保 anyrouter2openai.py 已启动并运行在 9999 端口）
PROXY_URL = "http://localhost:9999/v1/chat/completions"
MODELS_URL = "http://localhost:9999/v1/models"

# 透传模式：必须提供有效的 anyrouter.top API Key
# 支持多 key 负载均衡，用逗号分隔
API_KEY = "sk-kkkkk"


async def test_non_stream():
    print("\n--- 测试非流式响应 ---")
    payload = {
        "model": "claude-sonnet-4-6",
        "max_tokens": 1024,
        "messages": [
            {"role": "user", "content": "你好，请自我介绍一下。"}
        ],
        "stream": False
    }

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(PROXY_URL, json=payload, headers=headers)
            if response.status_code == 200:
                result = response.json()
                print("成功！")
                print(f"模型: {result['model']}")
                print(f"回答内容: {result['choices'][0]['message']['content']}")
                print(f"Token 使用: {result['usage']}")
            else:
                print(f"失败！状态码: {response.status_code}")
                print(f"错误详情: {response.text}")
        except Exception as e:
            print(f"请求发生异常: {e}")


async def test_stream():
    print("\n--- 测试流式响应 ---")
    payload = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 1024,
        "messages": [
            {"role": "user", "content": "讲一个简短的笑话。"}
        ],
        "stream": True
    }

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            async with client.stream("POST", PROXY_URL, json=payload, headers=headers) as response:
                if response.status_code == 200:
                    print("成功！正在接收流式内容:")
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str == "[DONE]":
                                print("\n流式传输结束。")
                                break
                            try:
                                data = json.loads(data_str)
                                if "error" in data:
                                    print(f"\n错误: {data['error']}")
                                    break
                                delta = data.get("choices", [{}])[0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    print(content, end="", flush=True)
                            except json.JSONDecodeError:
                                pass
                else:
                    print(f"失败！状态码: {response.status_code}")
                    error_content = await response.aread()
                    print(f"错误详情: {error_content.decode()}")
        except Exception as e:
            print(f"请求发生异常: {e}")


async def test_models():
    print("\n--- 测试获取模型列表 ---")
    headers = {
        "Authorization": f"Bearer {API_KEY}",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(MODELS_URL, headers=headers)
            if response.status_code == 200:
                result = response.json()
                print("成功！可用模型:")
                for model in result.get("data", [])[:5]:  # 只显示前5个
                    print(f"  - {model.get('id', 'unknown')}")
                if len(result.get("data", [])) > 5:
                    print(f"  ... 共 {len(result['data'])} 个模型")
            else:
                print(f"失败！状态码: {response.status_code}")
                print(f"错误详情: {response.text}")
        except Exception as e:
            print(f"请求发生异常: {e}")


async def test_no_auth():
    print("\n--- 测试无认证请求 (预期 401 错误) ---")
    payload = {
        "model": "claude-haiku-4-5-20251001",
        "messages": [{"role": "user", "content": "hello"}],
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(PROXY_URL, json=payload)
            print(f"状态码: {response.status_code}")
            print(f"响应: {response.text}")
        except Exception as e:
            print(f"请求发生异常: {e}")


async def main():
    print("=" * 50)
    print("AnyRouter OpenAI Proxy 客户端测试")
    print("=" * 50)
    print(f"代理地址: {PROXY_URL}")
    print(f"API Key: {API_KEY[:10]}..." if len(API_KEY) > 10 else f"API Key: {API_KEY}")

    await test_no_auth()
    await test_models()
    await test_non_stream()
    await test_stream()


if __name__ == "__main__":
    asyncio.run(main())
