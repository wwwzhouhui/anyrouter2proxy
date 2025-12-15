# AnyRouter2Proxy Docker 部署指南

## 快速开始

### 1. 准备环境变量文件

```bash
# 复制示例配置文件
cp .env.example .env

# 编辑配置文件，填入你的 API Keys
vim .env
```

在 `.env` 文件中至少需要配置：
```bash
API_KEYS=your_api_key_1,your_api_key_2
```

### 2. 使用 Docker Compose 运行（推荐）

```bash
# 拉取镜像（如果还没有）
docker pull wwwzhouhui569/anyrouter2proxy:latest

# 启动两个代理服务
docker-compose up -d

# 查看运行状态
docker-compose ps

# 查看日志
docker-compose logs -f anthropic-proxy
docker-compose logs -f openai-proxy

# 停止服务
docker-compose down
```

### 3. 单独构建和运行

```bash
# 拉取已构建的镜像
docker pull wwwzhouhui569/anyrouter2proxy:latest

# 运行 Anthropic 代理服务
docker run -d \
  --name anyrouter-anthropic-proxy \
  -p 9998:9998 \
  -e RUN_MODE=anthropic \
  -e API_KEYS=your_api_keys \
  wwwzhouhui569/anyrouter2proxy:latest

# 运行 OpenAI 代理服务
docker run -d \
  --name anyrouter-openai-proxy \
  -p 9999:9999 \
  -e RUN_MODE=openai \
  -e API_KEYS=your_api_keys \
  wwwzhouhui569/anyrouter2proxy:latest
```

## 服务访问

- **Anthropic 代理**: http://localhost:9998
- **OpenAI 代理**: http://localhost:9999

### API 端点

#### Anthropic 代理 (端口 9998)
- `GET /` - 服务信息
- `GET /health` - 健康检查
- `GET /stats` - 负载均衡统计
- `GET /v1/models` - 列出可用模型
- `POST /v1/messages` - 发送消息

#### OpenAI 代理 (端口 9999)
- `GET /` - 服务信息
- `GET /health` - 健康检查
- `GET /stats` - 负载均衡统计
- `GET /v1/models` - 列出可用模型
- `POST /v1/chat/completions` - 聊天完成

## 环境变量说明

| 变量名 | 描述 | 默认值 |
|--------|------|--------|
| `API_KEYS` | 多个 API Key，用逗号分隔 | 必填 |
| `ANYROUTER_BASE_URL` | 上游 AnyRouter 服务地址 | https://anyrouter.top |
| `LOAD_BALANCE_STRATEGY` | 负载均衡策略 (round_robin/random/weighted) | round_robin |
| `PORT` | Anthropic 代理端口 | 9998 |
| `OPENAI_PROXY_PORT` | OpenAI 代理端口 | 9999 |
| `HOST` | 绑定地址 | 0.0.0.0 |
| `HTTP_TIMEOUT` | HTTP 请求超时时间(秒) | 120 |
| `DEFAULT_MAX_TOKENS` | 默认最大 tokens | 8192 |
| `FORCE_NON_STREAM` | 强制非流式 (OpenAI 代理) | false |
| `DEFAULT_SYSTEM_PROMPT` | 默认系统提示词 | "You are Claude, a helpful AI assistant." |

## 监控和管理

### 查看服务统计
```bash
# Anthropic 代理统计
curl http://localhost:9998/stats

# OpenAI 代理统计
curl http://localhost:9999/stats
```

### 重启服务
```bash
docker-compose restart anthropic-proxy
docker-compose restart openai-proxy
```

### 更新服务
```bash
# 拉取最新镜像
docker-compose pull

# 重新启动
docker-compose up -d
```

## 日志管理

日志文件保存在 `./logs` 目录中：

```bash
# 查看实时日志
docker-compose logs -f

# 查看特定服务日志
docker-compose logs -f anthropic-proxy
docker-compose logs -f openai-proxy
```

## 故障排除

### 1. 容器无法启动
```bash
# 检查容器日志
docker-compose logs anthropic-proxy
docker-compose logs openai-proxy

# 检查环境变量
docker-compose config
```

### 2. API 调用失败
```bash
# 检查服务状态
curl http://localhost:9998/health
curl http://localhost:9999/health

# 查看统计信息
curl http://localhost:9998/stats
curl http://localhost:9999/stats
```

### 3. 端口冲突
如果 9998 或 9999 端口被占用，可以修改 `.env` 文件中的端口配置：
```bash
PORT=9998
OPENAI_PROXY_PORT=9999
```

然后重新启动服务。

## 生产环境部署

### 1. 使用环境变量文件
```bash
# 创建生产环境配置
cat > .env.prod << EOF
API_KEYS=your_production_api_keys
LOAD_BALANCE_STRATEGY=weighted
MAX_FAIL_COUNT=5
FAIL_RESET_SECONDS=120
EOF

# 使用生产配置启动
docker-compose --env-file .env.prod up -d
```

### 2. 数据持久化
```bash
# 创建数据目录
mkdir -p logs data

# 在 docker-compose.yml 中添加卷挂载
volumes:
  - ./logs:/app/logs
  - ./data:/app/data
```

### 3. 资源限制
在 `docker-compose.yml` 中添加资源限制：
```yaml
services:
  anthropic-proxy:
    deploy:
      resources:
        limits:
          cpus: '0.5'
          memory: 512M
        reservations:
          cpus: '0.25'
          memory: 256M
```
