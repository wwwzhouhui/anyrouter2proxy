# LLM API Protocol Converter Proxy

一个用于在 OpenAI 和 Anthropic API 协议之间进行双向转换的代理服务集合，支持多种部署方式，让你使用任意客户端 SDK 访问不同的后端服务。

## 什么是**AnyRouter.top**

**AnyRouter.top** 是一个提供 API 转发服务的中转站网站

- **用途**：帮助国内用户绕过网络限制，直接通过本地终端（如 VS Code 插件、Cursor 或命令行）调用 Claude 的 API。
- **现状**：目前该站点常被社区用于"白嫖"或低成本使用 Claude Code 功能

免费的公益站注册地址：https://anyrouter.top/register?aff=XYGH  每天登陆送25美金，可以使用https://github.com/wwwzhouhui/anyrouter-check-in 实现自定登录获取每天25美金积分

另外我们还提供下面的公益站和非公益站大家可以根据自己的需要选择使用

  下面是免费claude glm4.6 gpt5等第三方公益站
	第二公益站(agentrouter）平台可以抽奖有积分，登陆送25美金
	https://agentrouter.org/register?aff=u6Z4
	第三个非公益站 邀请新户送积分，可以充值
	https://api.codemirror.codes/register?aff=q9ke
     第四个非公益站，邀请新户送积分，可以充值（有gemini-3-pro-image-preview 模型）
	https://api.gemai.cc/register?aff=ND9Y
    第五个中间站，邀请新户送积分，可以充值（有gemini-3-pro-image-preview，有最新的gpt5.2）
    https://go.geeknow.top/register?aff=EdIn

​     第六个中间网站，邀请新户送积分，可以充值（有gemini-3-pro-image-preview）

   https://go.geeknow.top/register?aff=EdIn

   第七个付费站（支持sora2）

  https://api.jxincm.cn/register?aff=SeEB

   第八个非公益站，邀请新户送积分，可以充值

   https://api.cpass.cc/register?aff=vkvc

AnyRouter.top由于网络原因国内访问不方便，另外也不能直接在newapi做代理使用，不能实现api接口的调用，限制比较多。所以本项目借用2次中转和代理实现api接口和claude code 无限白嫖使用。

**免费体验地址**  http://115.190.165.156:3000/

**免费体验api key** :sk-eKU0nC4uERD0OVirefq6VgcD2FCwn7t7lvqy84c9xIQrlD1S    (100美金用完就止)

## 项目概述

本项目包含多个代理服务和客户端示例，实现了 OpenAI 和 Anthropic API 协议的互相转换：

### 🚀 **方案一：透传代理模式（推荐）**

| 文件 | 类型 | 说明 |
|------|------|------|
| `anyrouter2anthropic.py` | 代理服务 | AnyRouter 透传代理（Anthropic 协议），端口 9998 |
| `anyrouter2openai.py` | 代理服务 | AnyRouter 透传代理（OpenAI 协议），端口 9999 |
| `Dockerfile` | 容器配置 | Docker 镜像构建文件 |
| `docker-compose.yml` | 编排配置 | Docker Compose 服务编排 |
| `.env.example` | 环境配置 | 环境变量示例文件 |
| `test_openai_proxy.py` | 测试脚本 | OpenAI 代理测试客户端 |

**🎯 核心特性：**
- **透传模式**：客户端必须提供有效的 API Key，服务只做协议转换和中转
- **多 Key 负载均衡**：客户端可传递多个 Key（逗号分隔），自动轮询
- **无服务端密钥**：服务端不存储任何 API Key，更安全
- **简单部署**：一键 Docker Compose 启动

### 🏗️ **方案二：基于 LiteLLM + Render 代理转发**（原始方案）

| 文件 | 类型 | 说明 |
|------|------|------|
| `anthropic2openai_proxy.py` | 代理服务 | Anthropic -> OpenAI 协议转换代理 |
| `conf_anthropic20251212.yaml` | 配置文件 | LiteLLM 代理配置 |
| `openai_client.py` | 客户端 | OpenAI SDK 调用示例 |
| `anthropic_client.py` | 客户端 | Anthropic SDK 调用示例 |

## 代码调用关系图

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

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 透传代理模式（推荐）🌟

#### 特点
- ✅ **透传模式**：客户端必须提供有效的 API Key
- ✅ **多 Key 负载均衡**：支持逗号分隔的多个 Key 自动轮询
- ✅ **无服务端密钥**：更安全，不在服务端存储任何 Key
- ✅ **Docker 部署**：一行命令完成部署
- ✅ **健康检查**：内置监控接口

#### 启动服务

```bash
# 启动 Anthropic 协议代理（端口 9998）
python anyrouter2anthropic.py

# 启动 OpenAI 协议代理（端口 9999）
python anyrouter2openai.py
```

#### 客户端调用示例

##### OpenAI 协议代理

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

##### 多 Key 负载均衡

```python
import openai

# 多个 Key 用逗号分隔，代理会自动轮询
client = openai.OpenAI(
    api_key="sk-key1,sk-key2,sk-key3",
    base_url="http://localhost:9999/v1"
)
```

##### Anthropic 协议代理

```python
import anthropic

client = anthropic.Anthropic(
    api_key="sk-your-anyrouter-api-key",  # 必须提供有效的 API Key
    base_url="http://localhost:9998"
)

response = client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=1024,
    messages=[{"role": "user", "content": "你好"}]
)

print(response.content[0].text)
```

##### cURL 测试

```bash
# 测试 OpenAI 代理
curl -X POST http://localhost:9999/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-your-api-key" \
  -d '{
    "model": "claude-haiku-4-5-20251001",
    "messages": [{"role": "user", "content": "你好"}]
  }'

# 测试 Anthropic 代理
curl -X POST http://localhost:9998/v1/messages \
  -H "Content-Type: application/json" \
  -H "x-api-key: sk-your-api-key" \
  -d '{
    "model": "claude-haiku-4-5-20251001",
    "max_tokens": 1024,
    "messages": [{"role": "user", "content": "你好"}]
  }'

# 无 Key 测试（预期返回 401）
curl http://localhost:9999/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "test", "messages": []}'
```

### 3. Docker 部署

#### 快速启动

```bash
# 拉取镜像
docker pull wwwzhouhui569/anyrouter2proxy:latest

# 启动服务
docker-compose up -d

# 查看状态
docker-compose ps
```

#### 验证服务

```bash
# 健康检查
curl http://localhost:9998/health
curl http://localhost:9999/health

# 服务信息
curl http://localhost:9998/
curl http://localhost:9999/
```

### 4. 使用 LiteLLM 代理（原始方案）

```bash
# 启动 Anthropic -> OpenAI 协议转换代理
python anthropic2openai_proxy.py
# 或使用 LiteLLM
litellm --config conf_anthropic20251212.yaml --port 8088 --host 0.0.0.0
```

## 环境变量说明

### 透传代理配置

| 变量名 | 必填 | 默认值 | 说明 |
|--------|------|--------|------|
| `ANYROUTER_BASE_URL` | ❌ | `https://anyrouter.top` | AnyRouter 服务地址 |
| `PORT` | ❌ | `9998` | Anthropic 代理端口 |
| `OPENAI_PROXY_PORT` | ❌ | `9999` | OpenAI 代理端口 |
| `HOST` | ❌ | `0.0.0.0` | 绑定地址 |
| `HTTP_TIMEOUT` | ❌ | `120` | HTTP 请求超时时间（秒） |
| `DEFAULT_MAX_TOKENS` | ❌ | `8192` | 默认最大 tokens |
| `FORCE_NON_STREAM` | ❌ | `false` | 强制非流式模式 |
| `DEFAULT_SYSTEM_PROMPT` | ❌ | `You are Claude...` | 默认系统提示词 |

**注意**：透传模式不需要在服务端配置 `API_KEYS`，客户端必须提供有效的 API Key。

## API 端点

### anyrouter2anthropic.py (端口 9998)

| 端点 | 方法 | 说明 |
|------|------|------|
| `/v1/messages` | POST | Anthropic Messages API（需要 x-api-key 或 Authorization） |
| `/v1/models` | GET | 列出可用模型（需要认证） |
| `/health` | GET | 健康检查 |
| `/` | GET | 服务信息 |

### anyrouter2openai.py (端口 9999)

| 端点 | 方法 | 说明 |
|------|------|------|
| `/v1/chat/completions` | POST | OpenAI Chat Completions API（需要 Authorization） |
| `/v1/models` | GET | 列出可用模型（需要认证） |
| `/health` | GET | 健康检查 |
| `/` | GET | 服务信息 |

## 认证方式

### OpenAI 代理 (9999)

```
Authorization: Bearer sk-your-api-key
# 或多 Key 负载均衡
Authorization: Bearer sk-key1,sk-key2,sk-key3
```

### Anthropic 代理 (9998)

```
x-api-key: sk-your-api-key
# 或
Authorization: Bearer sk-your-api-key
# 多 Key 负载均衡
x-api-key: sk-key1,sk-key2,sk-key3
```

## 错误响应

### 未提供 API Key (401)

```json
{
  "error": {
    "message": "Authorization header required. Please provide a valid API key.",
    "type": "authentication_error"
  }
}
```

### API Key 无效（来自上游）

上游 AnyRouter 返回的错误会被透传给客户端。

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
├── # 🏗️ LiteLLM + Render 方案
├── anthropic2openai_proxy.py    # Anthropic -> OpenAI 代理 (端口 8088)
├── conf_anthropic20251212.yaml  # LiteLLM 配置文件
├── openai_client.py             # OpenAI SDK 客户端示例
├── anthropic_client.py          # Anthropic SDK 客户端示例
│
└── README.md                    # 本文档
```

## 使用场景

### 🚀 透传代理模式（推荐）

1. **安全部署**：不在服务端存储 API Key，每个用户使用自己的 Key
2. **多租户**：不同用户使用不同的 Key，互不影响
3. **负载均衡**：单用户多 Key 自动轮询
4. **协议转换**：使用 OpenAI SDK 调用 Claude 模型

### 🏗️ LiteLLM 方案

1. **快速原型**：无需本地部署，使用 Render 免费托管
2. **学习研究**：了解 LiteLLM 的配置和使用方式

## 部署实战

​    项目整体调用流程图如下

![流程调用图_精美版](https://mypicture-1258720957.cos.ap-nanjing.myqcloud.com/Obsidian/%E6%B5%81%E7%A8%8B%E8%B0%83%E7%94%A8%E5%9B%BE_%E7%B2%BE%E7%BE%8E%E7%89%88.png)

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

## 故障排除

### 常见问题

1. **401 Unauthorized**
   - 确保请求头包含有效的 API Key
   - OpenAI 协议使用 `Authorization: Bearer sk-xxx`
   - Anthropic 协议使用 `x-api-key: sk-xxx`

2. **服务无法访问**
   ```bash
   # 检查服务状态
   docker-compose ps
   docker-compose logs
   ```

3. **上游错误**
   - 检查 API Key 是否有效
   - 检查 AnyRouter 服务是否可用

---

通过透传模式，你可以安全、灵活地使用 AnyRouter 代理服务！
