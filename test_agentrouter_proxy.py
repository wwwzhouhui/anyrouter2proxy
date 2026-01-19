import httpx
import json
import asyncio

# 配置代理地址（请确保 anyrouter2anthropic_agentrouter.py 已启动并运行在 9997 端口）
PROXY_URL = "http://localhost:9998/v1/messages"
# 代理会自动替换为真实的 Key，所以这里填任意字符串即可
#DUMMY_API_KEY = "sk-dddd"
DUMMY_API_KEY = "sk-aaaaa"

async def test_non_stream():
    print("\n--- 测试非流式响应 ---")
    payload = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 1024,
        "messages": [
            {"role": "user", "content": "你好，请自我介绍一下。"}
        ],
        "stream": False
    }
    
    headers = {
        "x-api-key": DUMMY_API_KEY,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(PROXY_URL, json=payload, headers=headers)
            if response.status_code == 200:
                result = response.json()
                print("成功！")
                print(f"回答内容: {result['content'][0]['text']}")
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
        "x-api-key": DUMMY_API_KEY,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            async with client.stream("POST", PROXY_URL, json=payload, headers=headers) as response:
                if response.status_code == 200:
                    print("成功！正在接收流式内容:")
                    async for line in response.aiter_lines():
                        if not line: continue
                        print(f"DEBUG: {line}") # 打印所有原始行
                        if line.startswith("data: "):
                            data_str = line[6:]
                            try:
                                data = json.loads(data_str)
                                if data["type"] == "content_block_delta":
                                    print(data["delta"]["text"], end="", flush=True)
                            except json.JSONDecodeError:
                                pass
                    print("\n流式传输结束。")
                else:
                    print(f"失败！状态码: {response.status_code}")
                    error_content = await response.aread()
                    print(f"错误详情: {error_content.decode()}")
        except Exception as e:
            print(f"请求发生异常: {e}")

async def main():
    print("开始验证 AgentRouter 代理...")
    await test_non_stream()
    await test_stream()

if __name__ == "__main__":
    asyncio.run(main())
