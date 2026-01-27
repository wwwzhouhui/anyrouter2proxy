# AnyRouter2Proxy Docker 部署指南

## 架构概览

```
客户端 → Python 代理 (9998/9999) → Node.js 代理 (4000) → anyrouter.top
                                         ↑
                                  官方 Anthropic SDK
                                  (WAF 绕过 + TLS 指纹)
```

三个服务通过 Docker 网络互通，Python 代理通过 `NODE_PROXY_URL` 连接 Node.js 代理。

---

## 快速开始

### 1. 准备配置

```bash
cp .env.example .env
# 按需修改 .env 中的配置，默认值即可直接使用
```

### 2. Docker Compose 部署（推荐）

```bash
# 生产环境（使用预构建镜像）
docker-compose up -d

# 开发环境（本地构建镜像）
docker-compose -f docker-compose-dev.yml up -d

# 查看状态
docker-compose ps

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

启动顺序由 `depends_on` + `service_healthy` 自动保证：

```
node-proxy (4000) 启动并健康 → anthropic-proxy (9998) + openai-proxy (9999)
```

### 3. 验证服务

```bash
# Node.js 代理
curl http://localhost:4000/health

# Anthropic 代理（含 Node.js 状态）
curl http://localhost:9998/health

# OpenAI 代理（含 Node.js 状态）
curl http://localhost:9999/health
```

---

## 镜像构建

### 构建 Python 代理镜像

```bash
docker build -t anyrouter2proxy:latest .
```

### 构建 Node.js 代理镜像

```bash
docker build -t anyrouter-node-proxy:latest ./node-proxy
```

### 推送到 Docker Hub

```bash
docker tag anyrouter2proxy:latest wwwzhouhui569/anyrouter2proxy:latest
docker tag anyrouter-node-proxy:latest wwwzhouhui569/anyrouter-node-proxy:latest

docker push wwwzhouhui569/anyrouter2proxy:latest
docker push wwwzhouhui569/anyrouter-node-proxy:latest
```

---

## Docker Run 单独运行

适用于不使用 docker-compose 的场景，需要手动管理网络和启动顺序。

### 创建网络

```bash
docker network create anyrouter-proxy
```

### 启动 Node.js 代理（必须最先启动）

```bash
docker run -d \
  --name anyrouter-node-proxy \
  --network anyrouter-proxy \
  --restart unless-stopped \
  -p 4000:4000 \
  -e NODE_PROXY_PORT=4000 \
  -e ANYROUTER_BASE_URL=https://anyrouter.top \
  wwwzhouhui569/anyrouter-node-proxy:latest
```

### 启动 Anthropic 代理

```bash
docker run -d \
  --name anyrouter-anthropic-proxy \
  --network anyrouter-proxy \
  --restart unless-stopped \
  -p 9998:9998 \
  -e RUN_MODE=anthropic \
  -e NODE_PROXY_URL=http://anyrouter-node-proxy:4000 \
  -e PORT=9998 \
  -e HTTP_TIMEOUT=120 \
  -e DEFAULT_MAX_TOKENS=8192 \
  wwwzhouhui569/anyrouter2proxy:latest
```

### 启动 OpenAI 代理

```bash
docker run -d \
  --name anyrouter-openai-proxy \
  --network anyrouter-proxy \
  --restart unless-stopped \
  -p 9999:9999 \
  -e RUN_MODE=openai \
  -e NODE_PROXY_URL=http://anyrouter-node-proxy:4000 \
  -e OPENAI_PROXY_PORT=9999 \
  -e HTTP_TIMEOUT=120 \
  -e DEFAULT_MAX_TOKENS=8192 \
  wwwzhouhui569/anyrouter2proxy:latest
```

### 清理容器

```bash
docker stop anyrouter-node-proxy anyrouter-anthropic-proxy anyrouter-openai-proxy
docker rm anyrouter-node-proxy anyrouter-anthropic-proxy anyrouter-openai-proxy
docker network rm anyrouter-proxy
```

---

## 服务访问

| 服务 | 地址 | 说明 |
|------|------|------|
| Node.js 代理 | http://localhost:4000 | WAF 处理层（内部服务） |
| Anthropic 代理 | http://localhost:9998 | Anthropic 协议接口 |
| OpenAI 代理 | http://localhost:9999 | OpenAI 协议接口 |

---

## 环境变量

### Node.js 代理

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `NODE_PROXY_PORT` | `4000` | 监听端口 |
| `ANYROUTER_BASE_URL` | `https://anyrouter.top` | 上游服务地址 |

### Python 代理（通用）

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `RUN_MODE` | - | `anthropic` 或 `openai`（必填） |
| `NODE_PROXY_URL` | `http://127.0.0.1:4000` | Node.js 代理地址 |
| `HOST` | `0.0.0.0` | 绑定地址 |
| `HTTP_TIMEOUT` | `120` | 请求超时（秒） |
| `DEFAULT_MAX_TOKENS` | `8192` | 默认最大 tokens |

### Anthropic 代理专用

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `PORT` | `9998` | 监听端口 |

### OpenAI 代理专用

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `OPENAI_PROXY_PORT` | `9999` | 监听端口 |
| `FORCE_NON_STREAM` | `false` | 强制非流式后端 |
| `DEFAULT_SYSTEM_PROMPT` | `You are Claude...` | 默认系统提示词 |

---

## 运维管理

### 查看日志

```bash
# 全部日志
docker-compose logs -f

# 单个服务
docker-compose logs -f node-proxy
docker-compose logs -f anthropic-proxy
docker-compose logs -f openai-proxy
```

### 重启服务

```bash
# 重启单个服务
docker-compose restart node-proxy

# 重启全部
docker-compose restart
```

### 更新服务

```bash
# 拉取最新镜像
docker-compose pull

# 重启
docker-compose up -d
```

---

## 故障排除

### 容器无法启动

```bash
# 检查日志
docker-compose logs node-proxy
docker-compose logs anthropic-proxy

# 检查配置
docker-compose config
```

### health 显示 node_status: unreachable

Node.js 代理未就绪，检查：

```bash
# Node.js 代理是否运行
docker-compose ps node-proxy

# Node.js 代理日志
docker-compose logs node-proxy

# 直接测试
curl http://localhost:4000/health
```

### 端口冲突

修改 `.env` 中的端口配置后重启：

```bash
docker-compose down && docker-compose up -d
```
