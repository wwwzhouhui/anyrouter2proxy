# LLM API Protocol Converter Proxy

> 在 OpenAI 和 Anthropic API 协议之间进行双向转换的代理服务集合，支持多种部署方式，让你使用任意客户端 SDK 访问不同的后端服务

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.8+-blue.svg)
![FastAPI](https://img.shields.io/badge/fastapi-0.116+-green.svg)

---

## 什么是 AnyRouter.top

**AnyRouter.top** 是一个提供 API 转发服务的中转站网站。

- **用途**: 帮助国内用户绕过网络限制，直接通过本地终端调用 Claude 的 API
- **现状**: 常被社区用于低成本使用 Claude Code 功能

### 免费体验

- **体验地址**: http://115.190.165.156:3000/
- **体验 Key**: `sk-eKU0nC4uERD0OVirefq6VgcD2FCwn7t7lvqy84c9xIQrlD1S` (100 美金用完即止)

### 推荐站点

| 站点 | 类型 | 特点 |
|------|------|------|
| [AnyRouter.top](https://anyrouter.top/register?aff=XYGH) | 公益站 | 每天登录送 25 美金 |
| [AgentRouter](https://agentrouter.org/register?aff=u6Z4) | 公益站 | 可抽奖、登录送 25 美金 |
| [CodeMirror](https://api.codemirror.codes/register?aff=q9ke) | 非公益 | 邀请新户送积分 |
| [GemAI](https://api.gemai.cc/register?aff=ND9Y) | 非公益 | 有 gemini-3-pro-image-preview |
| [GeekNow](https://go.geeknow.top/register?aff=EdIn) | 非公益 | 有 gemini-3-pro-image-preview、gpt5.2 |
| [JXinCM](https://api.jxincm.cn/register?aff=SeEB) | 付费 | 支持 Sora2 |
| [CPass](https://api.cpass.cc/register?aff=vkvc) | 非公益 | 邀请新户送积分 |

---

## 项目介绍

本项目包含多个代理服务和客户端示例，实现了 OpenAI 和 Anthropic API 协议的互相转换。通过双重中转和代理实现 API 接口和 Claude Code 的便捷使用。

### 核心特性

- **双向协议转换**: OpenAI ↔ Anthropic 协议互相转换
- **透传代理模式**: 客户端提供 API Key，服务端只做协议转换
- **多 Key 负载均衡**: 支持逗号分隔的多个 Key 自动轮询
- **无服务端密钥**: 不在服务端存储任何 API Key
- **Docker 一键部署**: 简化部署流程

---

## 功能清单

| 功能名称 | 功能说明 | 技术栈 | 状态 |
|---------|---------|--------|------|
| OpenAI → Anthropic 转换 | OpenAI 格式转 Anthropic 格式 | FastAPI + httpx | ✅ 稳定 |
| Anthropic → OpenAI 转换 | Anthropic 格式转 OpenAI 格式 | FastAPI + httpx | ✅ 稳定 |
| 透传代理模式 | 客户端 Key 透传，无服务端存储 | FastAPI | ✅ 稳定 |
| 多 Key 负载均衡 | 自动轮询多个 API Key | Python | ✅ 稳定 |
| 流式响应支持 | SSE 流式输出 | httpx | ✅ 稳定 |
| 健康检查 | 内置监控接口 | FastAPI | ✅ 稳定 |
| LiteLLM 配置支持 | YAML 配置文件 | LiteLLM | ✅ 稳定 |

---

## 调用链路图

### 透传代理模式

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            调用链路：透传代理模式                                  │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│   ┌──────────────────┐       ┌─────────────────────────┐       ┌─────────────┐ │
│   │  客户端 (带 Key)  │ ───► │   anyrouter2openai.py   │ ───► │  AnyRouter  │ │
│   │  Authorization:   │       │   (协议转换 + 透传)      │       │  (Claude)   │ │
│   │  Bearer sk-xxx    │       │   端口 9999             │       │             │ │
│   └──────────────────┘       └─────────────────────────┘       └─────────────┘ │
│           │                            │                              │        │
│           ▼                            ▼                              ▼        │
│   OpenAI API 格式             OpenAI → Anthropic              Anthropic API    │
│   客户端提供 API Key          格式转换 + Key 透传            /v1/messages       │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Anthropic 协议透传

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            Anthropic 协议透传                                    │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│   ┌──────────────────┐       ┌──────────────────────────┐      ┌─────────────┐ │
│   │  客户端 (带 Key)  │ ───► │  anyrouter2anthropic.py  │ ───► │  AnyRouter  │ │
│   │  x-api-key:       │       │   (直接透传)              │       │  (Claude)   │ │
│   │  sk-xxx           │       │   端口 9998              │       │             │ │
│   └──────────────────┘       └──────────────────────────┘      └─────────────┘ │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 技术架构

| 技术 | 版本 | 用途 |
|------|------|------|
| Python | 3.8+ | 主要开发语言 |
| FastAPI | 0.116+ | Web 框架 |
| httpx | 0.28+ | 异步 HTTP 客户端 |
| Uvicorn | 0.35+ | ASGI 服务器 |
| Pydantic | 2.5+ | 数据验证 |
| LiteLLM | latest | 多模型路由 |

---

## 安装说明

### 环境要求

- Python 3.8+
- pip 包管理器

### 安装依赖

```bash
pip install -r requirements.txt
```

---

## 使用说明

### 透传代理模式（推荐）

#### 特点

- ✅ **透传模式**: 客户端必须提供有效的 API Key
- ✅ **多 Key 负载均衡**: 支持逗号分隔的多个 Key 自动轮询
- ✅ **无服务端密钥**: 更安全，不在服务端存储任何 Key
- ✅ **Docker 部署**: 一行命令完成部署
- ✅ **健康检查**: 内置监控接口

#### 启动服务

```bash
# 启动 Anthropic 协议代理（端口 9998）
python anyrouter2anthropic.py

# 启动 OpenAI 协议代理（端口 9999）
python anyrouter2openai.py
```

#### OpenAI 协议代理调用

```python
import openai

client = openai.OpenAI(
    api_key="sk-your-anyrouter-api-key",  # 必须提供有效的 API Key
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

#### 多 Key 负载均衡

```python
import openai

# 多个 Key 用逗号分隔，代理会自动轮询
client = openai.OpenAI(
    api_key="sk-key1,sk-key2,sk-key3",
    base_url="http://localhost:9999/v1"
)
```

#### Anthropic 协议代理调用

```python
import anthropic

client = anthropic.Anthropic(
    api_key="sk-your-anyrouter-api-key",
    base_url="http://localhost:9998"
)

response = client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=1024,
    messages=[{"role": "user", "content": "你好"}]
)

print(response.content[0].text)
```

---

## 配置说明

### 环境变量配置

| 变量名 | 必填 | 默认值 | 说明 |
|--------|------|--------|------|
| `ANYROUTER_BASE_URL` | ❌ | `https://anyrouter.top` | AnyRouter 服务地址 |
| `PORT` | ❌ | `9998` | Anthropic 代理端口 |
| `OPENAI_PROXY_PORT` | ❌ | `9999` | OpenAI 代理端口 |
| `HOST` | ❌ | `0.0.0.0` | 绑定地址 |
| `HTTP_TIMEOUT` | ❌ | `120` | HTTP 请求超时时间（秒） |
| `DEFAULT_MAX_TOKENS` | ❌ | `8192` | 默认最大 tokens |
| `FORCE_NON_STREAM` | ❌ | `false` | 强制非流式模式 |

**注意**: 透传模式不需要在服务端配置 `API_KEYS`，客户端必须提供有效的 API Key。

---

## API 端点

### anyrouter2anthropic.py (端口 9998)

| 端点 | 方法 | 说明 |
|------|------|------|
| `/v1/messages` | POST | Anthropic Messages API |
| `/v1/models` | GET | 列出可用模型 |
| `/health` | GET | 健康检查 |
| `/` | GET | 服务信息 |

### anyrouter2openai.py (端口 9999)

| 端点 | 方法 | 说明 |
|------|------|------|
| `/v1/chat/completions` | POST | OpenAI Chat Completions API |
| `/v1/models` | GET | 列出可用模型 |
| `/health` | GET | 健康检查 |
| `/` | GET | 服务信息 |

---

## 认证方式

### OpenAI 代理 (9999)

```http
Authorization: Bearer sk-your-api-key
# 或多 Key 负载均衡
Authorization: Bearer sk-key1,sk-key2,sk-key3
```

### Anthropic 代理 (9998)

```http
x-api-key: sk-your-api-key
# 或
Authorization: Bearer sk-your-api-key
# 多 Key 负载均衡
x-api-key: sk-key1,sk-key2,sk-key3
```

---

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

---

## 项目结构

```
anyrouter2proxy/
├── # 🚀 透传代理模式（推荐）
├── anyrouter2anthropic.py       # Anthropic 协议透传代理 (端口 9998)
├── anyrouter2openai.py          # OpenAI 协议透传代理 (端口 9999)
├── test_openai_proxy.py         # OpenAI 代理测试脚本
├── Dockerfile                    # Docker 镜像构建文件
├── docker-compose.yml           # Docker Compose 服务编排
├── docker-compose-dev.yml       # 开发环境 Docker Compose
├── .env.example                 # 环境变量示例文件
├── requirements.txt             # Python 依赖包
├── DOCKER.md                    # Docker 部署详细指南
│
├── # 🏗️ LiteLLM 方案
├── anthropic2openai_proxy.py    # Anthropic -> OpenAI 代理 (端口 8088)
├── conf_anthropic20251212.yaml  # LiteLLM 配置文件
├── openai_client.py             # OpenAI SDK 客户端示例
├── anthropic_client.py          # Anthropic SDK 客户端示例
│
└── README.md                    # 本文档
```

---

## 开发指南

### 本地开发

```bash
# 安装依赖
pip install -r requirements.txt

# 启动 Anthropic 协议代理
python anyrouter2anthropic.py

# 启动 OpenAI 协议代理
python anyrouter2openai.py

# 测试 OpenAI 代理
python test_openai_proxy.py
```

### Docker 开发

```bash
# 拉取镜像
docker pull wwwzhouhui569/anyrouter2proxy:latest

# 启动服务
docker-compose up -d

# 查看状态
docker-compose ps

# 查看日志
docker-compose logs -f
```

---

## 部署指南

### Docker 一键部署

```bash
# 1. 克隆项目
git clone <your-repo>
cd anyrouter2proxy

# 2. 启动服务（透传模式，无需配置 API Key）
docker-compose up -d

# 3. 验证服务
curl http://localhost:9998/health
curl http://localhost:9999/health

# 4. 测试调用（需要提供你的 API Key）
curl -X POST http://localhost:9999/v1/chat/completions \
  -H "Authorization: Bearer sk-your-anyrouter-api-key" \
  -H "Content-Type: application/json" \
  -d '{"model": "claude-haiku-4-5-20251001", "messages": [{"role": "user", "content": "你好"}]}'
```

### Claude Code 配置

使用 cc-switch 配置：

```json
{
  "env": {
    "ANTHROPIC_AUTH_TOKEN": "sk-your-anyrouter-api-key",
    "ANTHROPIC_BASE_URL": "http://localhost:9998",
    "ANTHROPIC_MODEL": "claude-haiku-4-5-20251001"
  }
}
```

### Cherry Studio 配置

1. 添加新的 API 提供商
2. API 地址：`http://localhost:9999/v1`（OpenAI）或 `http://localhost:9998`（Anthropic）
3. API Key：填入你的 anyrouter.top API Key
4. 选择模型并开始使用

---

## 常见问题

<details>
<summary>Q: 401 Unauthorized 错误？</summary>

A: 确保请求头包含有效的 API Key。OpenAI 协议使用 `Authorization: Bearer sk-xxx`，Anthropic 协议使用 `x-api-key: sk-xxx`。
</details>

<details>
<summary>Q: 服务无法访问？</summary>

A: 检查服务状态：`docker-compose ps` 和 `docker-compose logs`。
</details>

<details>
<summary>Q: 上游错误？</summary>

A: 检查 API Key 是否有效，检查 AnyRouter 服务是否可用。
</details>

<details>
<summary>Q: 如何使用多个 API Key？</summary>

A: 在客户端将多个 Key 用逗号分隔，如 `sk-key1,sk-key2,sk-key3`，代理会自动轮询。
</details>

<details>
<summary>Q: 支持流式响应吗？</summary>

A: 是的，两个代理都完整支持 SSE 流式输出。客户端 SDK 设置 `stream=True` 即可。
</details>

<details>
<summary>Q: 如何在服务端配置 API Key？</summary>

A: 透传模式不支持服务端配置 API Key，必须由客户端提供。如需服务端配置，请使用 LiteLLM 方案。
</details>

---

## 使用场景

### 透传代理模式（推荐）

1. **安全部署**: 不在服务端存储 API Key，每个用户使用自己的 Key
2. **多租户**: 不同用户使用不同的 Key，互不影响
3. **负载均衡**: 单用户多 Key 自动轮询
4. **协议转换**: 使用 OpenAI SDK 调用 Claude 模型

### LiteLLM 方案

1. **快速原型**: 无需本地部署，使用 Render 免费托管
2. **学习研究**: 了解 LiteLLM 的配置和使用方式

---

## 整体调用流程

![调用流程图](https://mypicture-1258720957.cos.ap-nanjing.myqcloud.com/Obsidian/%E6%B5%81%E7%A8%8B%E8%B0%83%E7%94%A8%E5%9B%BE_%E7%B2%BE%E7%BE%8E%E7%89%88.png)

---

## License

MIT License

---

## 技术交流群

欢迎加入技术交流群，分享你的使用心得和反馈建议：

![技术交流群](https://mypicture-1258720957.cos.ap-nanjing.myqcloud.com/Obsidian/image-20260122235736120.png)

---

## 作者联系

- **微信**: laohaibao2025
- **邮箱**: 75271002@qq.com

![微信二维码](https://mypicture-1258720957.cos.ap-nanjing.myqcloud.com/Screenshot_20260123_095617_com.tencent.mm.jpg)

---

## 打赏

如果这个项目对你有帮助，欢迎请我喝杯咖啡 ☕

**微信支付**

![微信支付](https://mypicture-1258720957.cos.ap-nanjing.myqcloud.com/Obsidian/image-20250914152855543.png)

---

## Star History

如果觉得项目不错，欢迎点个 Star ⭐

[![Star History Chart](https://api.star-history.com/svg?repos=wwwzhouhui/anyrouter2proxy&type=Date)](https://star-history.com/#wwwzhouhui/anyrouter2proxy&Date)
