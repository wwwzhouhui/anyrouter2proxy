# LLM API Protocol Converter Proxy

一个用于在 OpenAI 和 Anthropic API 协议之间进行双向转换的代理服务集合，让你可以使用任意客户端 SDK 访问不同的后端服务。

## 项目概述

本项目包含多个代理服务和客户端示例，实现了 OpenAI 和 Anthropic API 协议的互相转换：

| 文件 | 类型 | 说明 |
|------|------|------|
| `anyrouter2openai.py` | 代理服务 | OpenAI -> Anthropic 协议转换代理 |
| `anthropic2openai_proxy.py` | 代理服务 | Anthropic -> OpenAI 协议转换代理 |
| `conf_anthropic20251212.yaml` | 配置文件 | LiteLLM 代理配置（等同于 anthropic2openai_proxy.py） |
| `openai_client.py` | 客户端 | OpenAI SDK 调用示例 |
| `anthropic_client.py` | 客户端 | Anthropic SDK 调用示例 |

## 代码调用关系图

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            调用链路一：OpenAI SDK 访问 Claude                      │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│   ┌──────────────────┐       ┌─────────────────────────┐       ┌─────────────┐ │
│   │  openai_client.py │ ───► │   anyrouter2openai.py   │ ───► │  AnyRouter  │ │
│   │  (OpenAI SDK)     │       │   (协议转换代理)         │       │  (Claude)   │ │
│   └──────────────────┘       └─────────────────────────┘       └─────────────┘ │
│           │                            │                              │        │
│           ▼                            ▼                              ▼        │
│   OpenAI API 格式             OpenAI → Anthropic              Anthropic API    │
│   /v1/chat/completions        格式转换                        /v1/messages     │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────┐
│                         调用链路二：Anthropic SDK 访问 OpenAI 兼容后端             │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│   方案 A：使用自定义代理                                                          │
│   ┌────────────────────┐     ┌───────────────────────────┐     ┌─────────────┐ │
│   │ anthropic_client.py │ ──► │ anthropic2openai_proxy.py │ ──► │ OpenAI 后端 │ │
│   │  (Anthropic SDK)    │     │   (协议转换代理)           │     │             │ │
│   └────────────────────┘     └───────────────────────────┘     └─────────────┘ │
│                                                                                 │
│   方案 B：使用 LiteLLM 代理                                                       │
│   ┌────────────────────┐     ┌───────────────────────────┐     ┌─────────────┐ │
│   │ anthropic_client.py │ ──► │ LiteLLM (使用 yaml 配置)   │ ──► │ OpenAI 后端 │ │
│   │  (Anthropic SDK)    │     │ conf_anthropic20251212.yaml│     │             │ │
│   └────────────────────┘     └───────────────────────────┘     └─────────────┘ │
│           │                            │                              │        │
│           ▼                            ▼                              ▼        │
│   Anthropic API 格式          Anthropic → OpenAI            OpenAI API 格式    │
│   /v1/messages                格式转换                      /v1/chat/completions│
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 详细数据流程图

```
                    ┌─────────────────────────────────────────┐
                    │              远程服务                    │
                    │                                         │
                    │  ┌─────────────────────────────────┐   │
                    │  │      https://anyrouter.top       │   │
                    │  │        (Anthropic API)           │   │
                    │  └──────────────▲──────────────────┘   │
                    │                 │                       │
                    │  ┌──────────────┼──────────────────┐   │
                    │  │  renderanyrouter2openai         │   │
                    │  │  .duckcloud.fun/v1              │   │
                    │  │  (OpenAI API - 部署的代理)       │   │
                    │  └──────────────▲──────────────────┘   │
                    └─────────────────┼───────────────────────┘
                                      │
              ┌───────────────────────┴────────────────────────┐
              │                                                │
              │              本地代理服务层                      │
              │                                                │
    ┌─────────┴─────────┐                     ┌────────────────┴─────────────┐
    │                   │                     │                              │
    │ anyrouter2openai  │                     │  anthropic2openai_proxy.py   │
    │      .py          │                     │         或                    │
    │                   │                     │  LiteLLM + yaml 配置          │
    │  端口: 9999        │                     │                              │
    │  输入: OpenAI 格式 │                     │  端口: 8088                   │
    │  输出: Anthropic   │                     │  输入: Anthropic 格式         │
    │        格式        │                     │  输出: OpenAI 格式            │
    └─────────▲─────────┘                     └──────────────▲───────────────┘
              │                                              │
              │                                              │
    ┌─────────┴─────────┐                     ┌──────────────┴───────────────┐
    │                   │                     │                              │
    │ openai_client.py  │                     │   anthropic_client.py        │
    │  (OpenAI SDK)     │                     │   (Anthropic SDK)            │
    │                   │                     │                              │
    └───────────────────┘                     └──────────────────────────────┘
              │                                              │
              │                                              │
              ▼                                              ▼
    ┌───────────────────┐                     ┌──────────────────────────────┐
    │  用户使用 OpenAI   │                     │  用户使用 Anthropic SDK       │
    │  SDK 调用 Claude  │                     │  调用 OpenAI 兼容后端         │
    └───────────────────┘                     └──────────────────────────────┘
```

## 快速开始

### 1. 安装依赖

```bash
pip install fastapi uvicorn httpx openai anthropic litellm
```

### 2. 场景一：使用 OpenAI SDK 访问 Claude

#### 启动代理服务

```bash
# 启动 OpenAI -> Anthropic 协议转换代理
python anyrouter2openai.py
# 代理运行在 http://localhost:9999
```

#### 运行客户端

```bash
python openai_client.py
```

或在代码中使用：

```python
import openai

client = openai.OpenAI(
    api_key="your-anyrouter-api-key",
    base_url="http://localhost:9999/v1"
)

response = client.chat.completions.create(
    model="claude-haiku-4-5-20251001",
    messages=[{"role": "user", "content": "你好"}],
    stream=True
)

for chunk in response:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")
```

### 3. 场景二：使用 Anthropic SDK 访问 OpenAI 兼容后端

#### 方案 A：使用自定义代理

```bash
# 启动 Anthropic -> OpenAI 协议转换代理
python anthropic2openai_proxy.py
# 代理运行在 http://localhost:8088
```

#### 方案 B：使用 LiteLLM 代理

```bash
# 使用 LiteLLM 启动代理
litellm --config conf_anthropic20251212.yaml --port 8088 --host 0.0.0.0
nohup litellm --config conf_anthropic20251212.yaml --port 8088 --host 0.0.0.0 > conf_anthropic20251212.log 2>&1 &
```

#### 运行客户端

```bash
python anthropic_client.py
```

或在代码中使用：

```python
import anthropic

client = anthropic.Anthropic(
    api_key="sk-litellm-anthropic-proxy-2024",
    base_url="http://127.0.0.1:8088"
)

with client.messages.stream(
    model="claude-haiku-4-5-20251001",
    max_tokens=1024,
    messages=[{"role": "user", "content": "你好"}],
) as stream:
    for text in stream.text_stream:
        print(text, end="")
```

## 配置说明

### anyrouter2openai.py 配置

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `ANYROUTER_BASE_URL` | `https://anyrouter.top` | AnyRouter 后端地址 |
| `FORCE_NON_STREAM` | `false` | 强制后端使用非流式请求 |

### anthropic2openai_proxy.py 配置

在代码中直接修改：

```python
OPENAI_API_BASE = "https://renderanyrouter2openai.duckcloud.fun/v1"
OPENAI_API_KEY = "your-api-key"
PROXY_PORT = 8088
```

### LiteLLM 配置 (conf_anthropic20251212.yaml)

```yaml
model_list:
  - model_name: "claude-haiku-4-5-20251001"
    litellm_params:
      model: "openai/claude-haiku-4-5-20251001"
      api_base: "https://renderanyrouter2openai.duckcloud.fun/v1"
      api_key: "your-api-key"
      custom_llm_provider: "openai"
```

## 支持的模型

| 模型名称 | 说明 |
|---------|------|
| `claude-haiku-4-5-20251001` | Claude Haiku 4.5 |
| `claude-3-5-haiku-20241022` | Claude 3.5 Haiku |
| `claude-3-5-sonnet-20241022` | Claude 3.5 Sonnet |
| `claude-3-7-sonnet-20250219` | Claude 3.7 Sonnet |
| `claude-opus-4-5-20251101` | Claude Opus 4.5 |
| `claude-sonnet-4-20250514` | Claude Sonnet 4 |
| `claude-sonnet-4-5-20250929` | Claude Sonnet 4.5 |

## API 端点

### anyrouter2openai.py (端口 9999)

| 端点 | 方法 | 说明 |
|------|------|------|
| `/v1/chat/completions` | POST | OpenAI Chat Completions API |
| `/v1/models` | GET | 列出可用模型 |
| `/health` | GET | 健康检查 |

### anthropic2openai_proxy.py (端口 8088)

| 端点 | 方法 | 说明 |
|------|------|------|
| `/v1/messages` | POST | Anthropic Messages API |
| `/v1/models` | GET | 列出可用模型 |
| `/health` | GET | 健康检查 |

## 协议转换说明

### OpenAI -> Anthropic 转换

| OpenAI 字段 | Anthropic 字段 |
|------------|----------------|
| `messages[role=system]` | `system` |
| `messages[role=user/assistant]` | `messages` |
| `max_tokens` | `max_tokens` |
| `temperature` | `temperature` |
| `top_p` | `top_p` |
| `stop` | `stop_sequences` |

### Anthropic -> OpenAI 转换

| Anthropic 字段 | OpenAI 字段 |
|---------------|-------------|
| `system` | `messages[role=system]` |
| `messages` | `messages` |
| `max_tokens` | `max_tokens` |
| `temperature` | `temperature` |
| `top_p` | `top_p` |
| `stop_sequences` | `stop` |

## 项目结构

```
litellm/
├── anyrouter2openai.py      # OpenAI -> Anthropic 代理 (端口 9999)
├── anthropic2openai_proxy.py # Anthropic -> OpenAI 代理 (端口 8088)
├── conf_anthropic20251212.yaml # LiteLLM 配置文件
├── openai_client.py         # OpenAI SDK 客户端示例
├── anthropic_client.py      # Anthropic SDK 客户端示例
└── README.md                # 本文档
```

## 使用场景

1. **使用熟悉的 SDK**：如果你习惯使用 OpenAI SDK，可以通过 `anyrouter2openai.py` 代理访问 Claude 模型
2. **统一 API 接口**：企业内部统一使用一种 API 格式，通过代理转换访问不同的 LLM 服务
3. **开发测试**：在本地开发时快速切换不同的 LLM 后端

## License

MIT
