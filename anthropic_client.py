"""
Anthropic SDK Client via LiteLLM Proxy

Call chain: aa.py (Anthropic SDK) --> LiteLLM Proxy --> https://renderanyrouter2openai.duckcloud.fun/v1

This script uses the native Anthropic SDK to call the LiteLLM proxy,
which should convert requests to OpenAI format and forward to the remote service.
"""

import anthropic

# Initialize Anthropic client pointing to LiteLLM proxy
client = anthropic.Anthropic(
    api_key="sk-litellm-anthropic-proxy-2024",  # LiteLLM proxy master key
    base_url="http://127.0.0.1:8088"   # LiteLLM proxy address
)

# Build conversation messages (Anthropic format)
messages = [
    {"role": "user", "content": "你好，你是谁啊"}
]

print("正在通过 LiteLLM 代理调用...")
print("调用链路：aa.py (Anthropic SDK) --> LiteLLM Proxy --> https://renderanyrouter2openai.duckcloud.fun/v1\n")

try:
    print("响应内容：\n" + "="*50)

    # Stream API call using Anthropic messages format
    with client.messages.stream(
        model="claude-haiku-4-5-20251001",  # Model name
        max_tokens=1024,
        messages=messages,
        temperature=0.7,
    ) as stream:
        for text in stream.text_stream:
            print(text, end="", flush=True)

    print("\n" + "="*50)
    print("\n调用成功!")
    print("完整调用链路:")
    print("   aa.py (Anthropic SDK)")
    print("     ↓")
    print("   LiteLLM Proxy (Anthropic -> OpenAI 协议转换)")
    print("     ↓")
    print("   https://renderanyrouter2openai.duckcloud.fun/v1 (远程 OpenAI 服务)")

except anthropic.APIConnectionError as e:
    print(f"\n连接错误: {e}")
    print("\n请确保 LiteLLM 代理正在运行:")
    print("  litellm --config conf_anthropic20251212.yaml --port 8088 --host 0.0.0.0")
except anthropic.APIStatusError as e:
    print(f"\nAPI 错误: {e.status_code}")
    print(f"错误信息: {e.message}")
    print("\n如果 LiteLLM 不支持此转换，请使用自定义代理:")
    print("  python anthropic2openai_proxy.py")
except Exception as e:
    print(f"\n意外错误: {e}")
    print("\n请确保:")
    print("1. LiteLLM 代理正在运行")
    print("2. 网络连接正常")
