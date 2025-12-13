import openai

client = openai.OpenAI(
    api_key="sk-aaaaaaaaaaaaaa",  # 使用 https://anyrouter.top/  apik
    #base_url="http://localhost:7860/v1"  # 本地测试地址
    #base_url="https://cuijic-litellmclaude.hf.space/v1"  # HuggingFace Spaces 地址
    base_url="https://renderanyrouter2openai.duckcloud.fun/v1"  # /render 自定域名代码地址
)

messages = [{"content": "你好，你是谁啊", "role": "user"}]

# 通过 LiteLLM 代理调用
response = client.chat.completions.create(
    model="claude-haiku-4-5-20251001",  # 使用 config.yaml 中定义的模型名
    messages=messages,
    stream=True
)

for chunk in response:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
print()