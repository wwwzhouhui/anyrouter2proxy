# LLM API Protocol Converter Proxy

一个用于在 OpenAI 和 Anthropic API 协议之间进行双向转换的代理服务集合，支持多种部署方式，让你使用任意客户端 SDK 访问不同的后端服务。

## 项目概述

本项目包含多个代理服务和客户端示例，实现了 OpenAI 和 Anthropic API 协议的互相转换：

### 🏗️ **方案一：基于 LiteLLM + Render 代理转发**（原始方案）

| 文件 | 类型 | 说明 |
|------|------|------|
| `anyrouter2openai.py` | 代理服务 | OpenAI -> Anthropic 协议转换代理 |
| `anthropic2openai_proxy.py` | 代理服务 | Anthropic -> OpenAI 协议转换代理 |
| `conf_anthropic20251212.yaml` | 配置文件 | LiteLLM 代理配置（等同于 anthropic2openai_proxy.py） |
| `openai_client.py` | 客户端 | OpenAI SDK 调用示例 |
| `anthropic_client.py` | 客户端 | Anthropic SDK 调用示例 |

### 🚀 **方案二：直接代码代理 + Docker 部署**（新增方案）

| 文件 | 类型 | 说明 |
|------|------|------|
| `anyrouter2anthropic.py` | 代理服务 | AnyRouter 直接代理服务（Anthropic 协议） |
| `anyrouter2openai.py` | 代理服务 | AnyRouter 直接代理服务（OpenAI 协议） |
| `Dockerfile` | 容器配置 | Docker 镜像构建文件 |
| `docker-compose.yml` | 编排配置 | Docker Compose 服务编排 |
| `.env.example` | 环境配置 | 环境变量示例文件 |
| `DOCKER.md` | 部署文档 | Docker 部署详细指南 |

**🎯 核心优势：**
- **更简单**：直接代码代理，无需复杂的 LiteLLM 配置
- **更稳定**：原生 FastAPI + httpx，性能更优
- **更灵活**：支持多 API Key 负载均衡和故障转移
- **更容易部署**：一键 Docker Compose 启动
- **更易维护**：清晰的代码结构和完善的健康检查

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

### 4. 场景三：直接代码代理（推荐方案）🌟

#### 优势特点
- ✅ **零配置**：无需复杂设置，一键启动
- ✅ **负载均衡**：支持多 API Key 自动轮询
- ✅ **故障转移**：自动检测并切换不健康的账号
- ✅ **Docker 部署**：一行命令完成部署
- ✅ **健康检查**：内置监控和统计接口

#### 快速开始（Docker 部署）

##### 1. 准备环境变量

```bash
# 复制配置模板
cp .env.example .env

# 编辑配置文件，填入你的 API Keys
vim .env
```

在 `.env` 文件中至少需要配置：
```bash
API_KEYS=your_api_key_1,your_api_key_2
```

##### 2. 启动服务

```bash
# 拉取镜像（如果还没有）
docker pull wwwzhouhui569/anyrouter2proxy:latest

# 启动两个代理服务
docker-compose up -d

# 查看运行状态
docker-compose ps
```

##### 3. 测试服务

```bash
# 测试 Anthropic 代理
curl http://localhost:9998/health

# 测试 OpenAI 代理
curl http://localhost:9999/health

# 查看负载均衡统计
curl http://localhost:9998/stats
curl http://localhost:9999/stats
```

#### 手动部署（直接运行 Python）

##### 1. 安装依赖

```bash
pip install -r requirements.txt
```

##### 2. 配置环境变量

```bash
# 设置 AnyRouter API Keys
export API_KEYS="sk-key1,sk-key2,sk-key3"

# 设置上游服务地址（可选）
export ANYROUTER_BASE_URL="https://anyrouter.top"

# 设置负载均衡策略（可选：round_robin/random/weighted）
export LOAD_BALANCE_STRATEGY="round_robin"
```

##### 3. 启动服务

```bash
# 启动 Anthropic 协议代理（端口 9998）
python anyrouter2anthropic.py

# 启动 OpenAI 协议代理（端口 9999）
python anyrouter2openai.py
```

#### 客户端使用示例

##### 使用 OpenAI 代理

```python
import openai

client = openai.OpenAI(
    api_key="any-string-as-key",  # 任意字符串，代理会忽略
    base_url="http://localhost:9999/v1"  # OpenAI 代理地址
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

##### 使用 Anthropic 代理

```python
import anthropic

client = anthropic.Anthropic(
    api_key="any-string-as-key",  # 任意字符串，代理会忽略
    base_url="http://localhost:9998"  # Anthropic 代理地址
)

response = client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=1024,
    messages=[{"role": "user", "content": "你好"}],
    stream=True
)

for chunk in response:
    if chunk.type == "content_block_delta":
        print(chunk.delta.text, end="")
```

#### 环境变量说明

| 变量名 | 必填 | 默认值 | 说明 |
|--------|------|--------|------|
| `API_KEYS` | ✅ | - | 多个 AnyRouter API Key，用逗号分隔 |
| `ANYROUTER_BASE_URL` | ❌ | `https://anyrouter.top` | AnyRouter 服务地址 |
| `LOAD_BALANCE_STRATEGY` | ❌ | `round_robin` | 负载均衡策略：round_robin/random/weighted |
| `PORT` | ❌ | `9998` | Anthropic 代理端口 |
| `OPENAI_PROXY_PORT` | ❌ | `9999` | OpenAI 代理端口 |
| `HTTP_TIMEOUT` | ❌ | `120` | HTTP 请求超时时间（秒） |
| `DEFAULT_MAX_TOKENS` | ❌ | `8192` | 默认最大 tokens |
| `FORCE_NON_STREAM` | ❌ | `false` | 强制非流式模式（解决某些兼容性问题） |

## 配置说明

### 方案三：直接代码代理服务配置

#### anyrouter2anthropic.py 配置（端口 9998）

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `API_KEYS` | 必填 | 多个 AnyRouter API Key，用逗号分隔 |
| `ANYROUTER_BASE_URL` | `https://anyrouter.top` | AnyRouter 后端地址 |
| `LOAD_BALANCE_STRATEGY` | `round_robin` | 负载均衡策略：round_robin/random/weighted |
| `PORT` | `9998` | 服务端口 |
| `HOST` | `0.0.0.0` | 绑定地址 |
| `HTTP_TIMEOUT` | `120` | HTTP 请求超时时间（秒） |
| `DEFAULT_MAX_TOKENS` | `8192` | 默认最大 tokens |
| `MAX_FAIL_COUNT` | `3` | 连续失败多少次标记为不健康 |
| `FAIL_RESET_SECONDS` | `60` | 不健康账号多少秒后重试 |

#### anyrouter2openai.py 配置（端口 9999）

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `API_KEYS` | 必填 | 多个 AnyRouter API Key，用逗号分隔 |
| `ANYROUTER_BASE_URL` | `https://anyrouter.top` | AnyRouter 后端地址 |
| `LOAD_BALANCE_STRATEGY` | `round_robin` | 负载均衡策略：round_robin/random/weighted |
| `OPENAI_PROXY_PORT` | `9999` | 服务端口 |
| `HOST` | `0.0.0.0` | 绑定地址 |
| `HTTP_TIMEOUT` | `120` | HTTP 请求超时时间（秒） |
| `DEFAULT_MAX_TOKENS` | `8192` | 默认最大 tokens |
| `FORCE_NON_STREAM` | `false` | 强制后端使用非流式请求 |
| `DEFAULT_SYSTEM_PROMPT` | `You are Claude, a helpful AI assistant.` | 默认系统提示词 |
| `MAX_FAIL_COUNT` | `3` | 连续失败多少次标记为不健康 |
| `FAIL_RESET_SECONDS` | `60` | 不健康账号多少秒后重试 |

### 方案一和二：原始方案配置

#### anyrouter2openai.py 配置

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

### 方案三：直接代码代理服务

#### anyrouter2anthropic.py (端口 9998)

| 端点 | 方法 | 说明 |
|------|------|------|
| `/v1/messages` | POST | Anthropic Messages API |
| `/v1/models` | GET | 列出可用模型 |
| `/health` | GET | 健康检查 |
| `/stats` | GET | 负载均衡统计信息 |
| `/` | GET | 服务信息 |

#### anyrouter2openai.py (端口 9999)

| 端点 | 方法 | 说明 |
|------|------|------|
| `/v1/chat/completions` | POST | OpenAI Chat Completions API |
| `/v1/models` | GET | 列出可用模型 |
| `/health` | GET | 健康检查 |
| `/stats` | GET | 负载均衡统计信息 |
| `/` | GET | 服务信息 |

### 方案一和二：原始方案

#### anyrouter2openai.py (端口 9999)

| 端点 | 方法 | 说明 |
|------|------|------|
| `/v1/chat/completions` | POST | OpenAI Chat Completions API |
| `/v1/models` | GET | 列出可用模型 |
| `/health` | GET | 健康检查 |

#### anthropic2openai_proxy.py (端口 8088)

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
anyrouter2proxy/
├── # 🏗️ 方案一：LiteLLM + Render 代理转发
├── anyrouter2openai.py          # OpenAI -> Anthropic 代理 (端口 9999)
├── anthropic2openai_proxy.py    # Anthropic -> OpenAI 代理 (端口 8088)
├── conf_anthropic20251212.yaml  # LiteLLM 配置文件
├── openai_client.py             # OpenAI SDK 客户端示例
├── anthropic_client.py          # Anthropic SDK 客户端示例
│
├── # 🚀 方案二：直接代码代理 + Docker 部署（推荐）
├── anyrouter2anthropic.py       # AnyRouter 直接代理 (Anthropic 协议，端口 9998)
├── anyrouter2openai.py          # AnyRouter 直接代理 (OpenAI 协议，端口 9999)
├── Dockerfile                    # Docker 镜像构建文件
├── docker-compose.yml           # Docker Compose 服务编排
├── .env.example                 # 环境变量示例文件
├── requirements.txt             # Python 依赖包
├── DOCKER.md                    # Docker 部署详细指南
│
└── README.md                    # 本文档
```

## 使用场景

### 🚀 方案三：直接代码代理（推荐）

1. **生产环境部署**：使用 Docker Compose 一键部署，支持负载均衡和故障转移
2. **企业级应用**：需要稳定的 API 服务，支持多账号管理和健康监控
3. **开发者工具**：本地开发测试，支持快速启动和调试
4. **高并发场景**：利用 FastAPI + httpx 的高性能异步处理能力
5. **监控运维**：内置健康检查和统计接口，便于运维监控

### 🏗️ 方案一：LiteLLM + Render 代理转发

1. **快速原型**：无需本地部署，使用 Render 免费托管
2. **学习研究**：了解 LiteLLM 的配置和使用方式
3. **简单场景**：只需要基本的协议转换功能

### 通用使用场景

1. **使用熟悉的 SDK**：如果你习惯使用 OpenAI SDK，可以通过代理访问 Claude 模型
2. **统一 API 接口**：企业内部统一使用一种 API 格式，通过代理转换访问不同的 LLM 服务
3. **开发测试**：在本地开发时快速切换不同的 LLM 后端

## 部署实战

​    项目整体调用流程图如下

![流程调用图_精美版](https://mypicture-1258720957.cos.ap-nanjing.myqcloud.com/Obsidian/%E6%B5%81%E7%A8%8B%E8%B0%83%E7%94%A8%E5%9B%BE_%E7%B2%BE%E7%BE%8E%E7%89%88.png)

   我们可以在render平台上部署anyrouter2openai.py 代码，可以使用docker 方式部署

### render平台部署anyrouter2openai

   下载镜像

```
docker pull wwwzhouhui569/anyrouter2openai
```

  登录https://dashboard.render.com

  ![image-20251213114718219](https://mypicture-1258720957.cos.ap-nanjing.myqcloud.com/Obsidian/image-20251213114718219.png)

​    

选择一个美国区域

![image-20251213114819090](https://mypicture-1258720957.cos.ap-nanjing.myqcloud.com/Obsidian/image-20251213114819090.png)

设置环境变量，填写ANYROUTER_BASE_URL  和 https://anyrouter.top

![image-20251213115003801](https://mypicture-1258720957.cos.ap-nanjing.myqcloud.com/Obsidian/image-20251213115003801.png)

 创建完成后 我的远程端就部署完成了。 当然你也可以自定义域名https://anyrouter2openai.onrender.com/

![image-20251213115122736](https://mypicture-1258720957.cos.ap-nanjing.myqcloud.com/Obsidian/image-20251213115122736.png)

通过上面的部署我们就完成了anyrouter2openai 节点的代理部署。

### litellm代理

 接下来我们使用litellm 在国内服务器上部署conf_anthropic20251212.yaml 实现anthropic 转openai协议

 我这里使用我火山云服务器首选安装litellm  

```
 pip install litellm  
```

 确保服务器上安装完成litellm

![image-20251213115528379](https://mypicture-1258720957.cos.ap-nanjing.myqcloud.com/Obsidian/image-20251213115528379.png)

创建一个litellm文件夹 复制conf_anthropic20251212.yaml 在当前litellm文件夹下。

![image-20251213115633692](https://mypicture-1258720957.cos.ap-nanjing.myqcloud.com/Obsidian/image-20251213115633692.png)

启动litellm

```
nohup litellm --config conf_anthropic20251212.yaml --port 8088 --host 0.0.0.0 > conf_anthropic20251212.log 2>&1 &
```

![image-20251213115757310](https://mypicture-1258720957.cos.ap-nanjing.myqcloud.com/Obsidian/image-20251213115757310.png)

通过上面的步骤我们完成了litellm启动

### 使用newapi代理

接下来我们使用newapi 这个开源项目配置litellm 代理配置。这个new api  我也是部署在litellm这台机器上（国内机器）

![image-20251213120001533](https://mypicture-1258720957.cos.ap-nanjing.myqcloud.com/Obsidian/image-20251213120001533.png)

创建渠道管理-添加渠道

![image-20251213120159613](https://mypicture-1258720957.cos.ap-nanjing.myqcloud.com/Obsidian/image-20251213120159613.png)

​     其中秘钥和api地址分别是下面的

![image-20251213120306152](https://mypicture-1258720957.cos.ap-nanjing.myqcloud.com/Obsidian/image-20251213120306152.png)

  api地址就是litellm代理发布的地址，我的服务器是115.190.165.156  端口 8088

![image-20251213120435828](https://mypicture-1258720957.cos.ap-nanjing.myqcloud.com/Obsidian/image-20251213120435828.png)

  通过上面方式我们就在new api  添加好代理渠道了。

![image-20251213120501765](https://mypicture-1258720957.cos.ap-nanjing.myqcloud.com/Obsidian/image-20251213120501765.png)

###     验证测试

#####      cherry studio验证测试

 cherry studio 配置

​     ![image-20251213121818626](https://mypicture-1258720957.cos.ap-nanjing.myqcloud.com/Obsidian/image-20251213121818626.png)

 模型配置详细

![image-20251213121949143](https://mypicture-1258720957.cos.ap-nanjing.myqcloud.com/Obsidian/image-20251213121949143.png)

  ![image-20251213122019269](https://mypicture-1258720957.cos.ap-nanjing.myqcloud.com/Obsidian/image-20251213122019269.png)

#####    claude code 

​    我们使用cc-switch 配置

   ![image-20251213122232268](https://mypicture-1258720957.cos.ap-nanjing.myqcloud.com/Obsidian/image-20251213122232268.png)

 完成的配置文件

```
{
  "env": {
    "ANTHROPIC_AUTH_TOKEN": "sk-eKU0nC4uERD0OVirefq6VgcD2FCwn7t7lvqy84c9xIQrlD1S",
    "ANTHROPIC_BASE_URL": "http://115.190.165.156:3000",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "claude-haiku-4-5-20251001",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "claude-opus-4-5-20251101",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "claude-sonnet-4-5-20250929",
    "ANTHROPIC_MODEL": "claude-haiku-4-5-20251001"
  }
}
```

使用claude code 测试

![image-20251213122442449](https://mypicture-1258720957.cos.ap-nanjing.myqcloud.com/Obsidian/image-20251213122442449.png)

  我们在new api 模型调用

  ![image-20251213122537390](https://mypicture-1258720957.cos.ap-nanjing.myqcloud.com/Obsidian/image-20251213122537390.png)

原any router上的日志

![image-20251213122627367](https://mypicture-1258720957.cos.ap-nanjing.myqcloud.com/Obsidian/image-20251213122627367.png)

 通过上面的操作步骤我们完成了完整claude code 客户端+litellm +render代理转发+any router全过程。

---

## 部署实战：Docker 一键部署（推荐方案）

### 🚀 优势对比

| 特性 | LiteLLM + Render | Docker 直接部署 |
|------|------------------|-----------------|
| 部署复杂度 | 高（多步骤配置） | 极简（一键启动） |
| 负载均衡 | ❌ 不支持 | ✅ 支持多 API Key |
| 故障转移 | ❌ 不支持 | ✅ 自动切换 |
| 健康监控 | ❌ 无 | ✅ 完整统计接口 |
| 性能 | 中等 | 高（异步处理） |
| 维护成本 | 高 | 低 |

### 📦 Docker 部署步骤

#### 1. 准备环境

```bash
# 确保已安装 Docker 和 Docker Compose
docker --version
docker-compose --version

# 克隆或下载项目
git clone <your-repo>
cd anyrouter2proxy

# 复制环境配置
cp .env.example .env
```

#### 2. 配置 API Keys

编辑 `.env` 文件：

```bash
# 必填：AnyRouter API Keys（多个用逗号分隔）
API_KEYS=sk-key1,sk-key2,sk-key3

# 可选：负载均衡策略
LOAD_BALANCE_STRATEGY=round_robin  # round_robin/random/weighted

# 可选：服务端口
PORT=9998
OPENAI_PROXY_PORT=9999

# 可选：上游服务地址
ANYROUTER_BASE_URL=https://anyrouter.top
```

#### 3. 一键启动

```bash
# 启动所有服务
docker-compose up -d

# 查看启动状态
docker-compose ps

# 查看实时日志
docker-compose logs -f
```

#### 4. 验证部署

```bash
# 测试服务健康状态
curl http://localhost:9998/health
curl http://localhost:9999/health

# 查看负载均衡统计
curl http://localhost:9998/stats | jq
curl http://localhost:9999/stats | jq

# 测试 API 调用
curl -X POST http://localhost:9998/v1/messages \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer test-key" \
  -d '{
    "model": "claude-haiku-4-5-20251001",
    "max_tokens": 1024,
    "messages": [{"role": "user", "content": "你好"}]
  }'
```

### 🔧 高级配置

#### 生产环境优化

创建生产环境配置 `docker-compose.prod.yml`：

```yaml
version: '3.8'

services:
  anthropic-proxy:
    image: wwwzhouhui569/anyrouter2proxy:latest
    restart: unless-stopped
    environment:
      - RUN_MODE=anthropic
      - API_KEYS=${API_KEYS}
      - LOAD_BALANCE_STRATEGY=weighted
      - MAX_FAIL_COUNT=5
      - FAIL_RESET_SECONDS=120
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 1G
        reservations:
          cpus: '0.5'
          memory: 512M
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

  openai-proxy:
    image: wwwzhouhui569/anyrouter2proxy:latest
    restart: unless-stopped
    environment:
      - RUN_MODE=openai
      - API_KEYS=${API_KEYS}
      - LOAD_BALANCE_STRATEGY=weighted
      - MAX_FAIL_COUNT=5
      - FAIL_RESET_SECONDS=120
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 1G
        reservations:
          cpus: '0.5'
          memory: 512M
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

#### 使用生产配置启动

```bash
# 使用生产配置
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# 或创建 .env.prod 文件
cp .env .env.prod
# 编辑 .env.prod 配置生产环境参数
docker-compose --env-file .env.prod up -d
```

### 📊 监控和运维

#### 查看服务状态

```bash
# 实时查看服务状态
docker-compose ps

# 查看资源使用情况
docker stats

# 查看服务日志
docker-compose logs anthropic-proxy
docker-compose logs openai-proxy
```

#### 负载均衡统计

```bash
# Anthropic 代理统计
curl -s http://localhost:9998/stats | python -m json.tool

# OpenAI 代理统计
curl -s http://localhost:9999/stats | python -m json.tool
```

#### 更新服务

```bash
# 拉取最新镜像
docker-compose pull

# 重新启动服务
docker-compose up -d

# 清理旧镜像
docker image prune -f
```

### 🛠️ 故障排除

#### 常见问题

1. **端口占用**
```bash
# 查看端口占用
netstat -tulpn | grep 9998
netstat -tulpn | grep 9999

# 修改端口（在 .env 文件中）
PORT=9998
OPENAI_PROXY_PORT=9999
```

2. **API Key 无效**
```bash
# 检查日志
docker-compose logs anthropic-proxy
docker-compose logs openai-proxy

# 验证 API Keys
curl -H "Authorization: Bearer YOUR_API_KEY" https://anyrouter.top/v1/models
```

3. **服务启动失败**
```bash
# 查看详细错误
docker-compose logs

# 重新构建镜像
docker-compose build --no-cache

# 清理容器和网络
docker-compose down -v
docker system prune -f
```

### 🌟 性能优化建议

1. **合理配置资源限制**
2. **使用合适的负载均衡策略**
3. **定期监控服务状态**
4. **配置日志轮转**
5. **使用健康检查**

通过 Docker 部署，你可以轻松获得一个稳定、高性能的 LLM 代理服务！

