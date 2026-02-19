# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在本仓库中工作时提供指导。

## 项目概述

LLM API 协议转换代理，将 OpenAI/Anthropic 客户端桥接到 AnyRouter.top 上游。采用三层架构：Python 代理（协议转换）→ Node.js 代理（WAF 绕过 + Claude Code 请求伪装）→ 上游服务。

## 架构

```
OpenAI 客户端 (9999)      → anyrouter2openai.py    → node-proxy/server.mjs (4000) → anyrouter.top
Anthropic 客户端 (9998)   → anyrouter2anthropic.py  → node-proxy/server.mjs (4000) → anyrouter.top
Anthropic 客户端 (9997)   → anyrouter2anthropic_agentrouter.py → anyrouter.top（直连，无 WAF 绕过）
```

**Node.js 代理 (server.mjs)** 是关键层：提供正确的 TLS 指纹、解决 ACW WAF 挑战、注入 Claude Code 请求特征（请求头、系统提示、thinking 字段、SDK 指纹），并维护 Cookie 状态。

**Python 代理** 负责协议转换（OpenAI↔Anthropic）、多 Key 负载均衡，以及向 Node.js 透明转发请求头。

## 常用命令

```bash
# 安装依赖
pip install -r requirements.txt
cd node-proxy && npm install && cd ..

# 启动服务（Node.js 必须最先启动）
cd node-proxy && npm start          # 终端 1 - 端口 4000
python anyrouter2anthropic.py       # 终端 2 - 端口 9998
python anyrouter2openai.py          # 终端 3 - 端口 9999
python anyrouter2anthropic_agentrouter.py  # 可选 - 端口 9997（直连模式）

# 运行测试（需要代理服务已启动）
python test_agentrouter_proxy.py    # 测试 Anthropic 代理 (9998)
python test_openai_proxy.py         # 测试 OpenAI 代理 (9999)

# Docker
docker-compose -f docker-compose-dev.yml up -d   # 开发环境（本地构建）
docker-compose up -d                               # 生产环境（预构建镜像）

# 健康检查
curl http://localhost:4000/health
curl http://localhost:9998/health
curl http://localhost:9999/health
```

## 关键设计决策

- **请求头透传**：Python 代理将客户端的所有请求头（去除逐跳头）转发到 Node.js。由 Node.js 决定注入哪些默认值。这对 Claude Code 客户端至关重要，其请求头必须原样到达上游。
- **Claude Code 伪装仅在 Node.js 层实现**：所有 Claude Code 请求特征注入（User-Agent、anthropic-beta、系统提示、thinking、x-stainless-* SDK 指纹）均在 server.mjs 的 `callAnthropicApi()` 中完成。Python 代理不添加这些。
- **User-Agent 强制覆盖**：Node.js 始终将 User-Agent 替换为 `claude-cli/2.1.39`，无论客户端发送什么，以防止泄露 `python-httpx` 身份标识。
- **系统提示按条件注入**：Node.js 仅在 `body.system` 为空时注入 Claude Code 系统提示。因此 `anyrouter2openai.py` 不能设置默认系统提示——否则会阻止 Node.js 注入，导致高级模型出现"负载已达上限"错误。

## 环境变量

关键配置在 `.env` / `.env.agentrouter` 中：
- `ANYROUTER_BASE_URL` — 上游地址（默认：`https://anyrouter.top`）
- `NODE_PROXY_URL` — Python 服务连接 Node.js 代理的地址（默认：`http://127.0.0.1:4000`）
- `PORT` (9998)、`OPENAI_PROXY_PORT` (9999)、`NODE_PROXY_PORT` (4000)
- `HTTP_TIMEOUT` (120秒)、`DEFAULT_MAX_TOKENS` (8192)
- `FORCE_NON_STREAM` — OpenAI 代理强制使用非流式后端

## 协议转换流程（OpenAI → Anthropic）

`anyrouter2openai.py` 的转换逻辑：
- `messages[role=system]` → `system[]` 字段（仅当用户提供了 system 消息时）
- `messages[role=user/assistant]` → Anthropic 内容块格式的 `messages[]`
- `max_tokens`、`temperature`、`top_p`、`stop` → 映射到 Anthropic 对应参数
- 图片内容（data URI、URL）→ Anthropic 图片源格式
- 流式 SSE 事件：`content_block_delta` → OpenAI `chat.completion.chunk`

## WAF 挑战解决（Node.js）

`server.mjs` 处理 ACW WAF 挑战：检测 HTML 响应中的 `acw_sc__v2` + `arg1`，通过位置映射数组重排 + 固定密钥 XOR 运算生成 Cookie 值，通过 `CookieJar` 设置 Cookie，然后重试请求（最多 3 次）。
