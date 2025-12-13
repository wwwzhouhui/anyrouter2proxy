# LLM API Protocol Converter Proxy

一个用于在 OpenAI 和 Anthropic API 协议之间进行双向转换的代理服务集合，让你可以使用任意客户端 SDK 访问不同的后端服务。

## 什么是**AnyRouter.top** 

**AnyRouter.top** 是一个提供 API 转发服务的中转站网站

- **用途**：帮助国内用户绕过网络限制，直接通过本地终端（如 VS Code 插件、Cursor 或命令行）调用 Claude 的 API。
- **现状**：目前该站点常被社区用于“白嫖”或低成本使用 Claude Code 功能

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

AnyRouter.top由于网络原因国内访问不方便，另外也不能直接在newapi做代理使用，不能实现api接口的调用，限制比较多。所以本项目借用2次中转和代理实现api接口和claude code 无限白嫖使用。

**免费体验地址**  http://115.190.165.156:3000/

**免费体验api key** :sk-eKU0nC4uERD0OVirefq6VgcD2FCwn7t7lvqy84c9xIQrlD1S    (100美金用完就止)

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

