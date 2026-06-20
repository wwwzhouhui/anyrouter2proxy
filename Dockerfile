FROM node:22-slim AS admin-ui-build

WORKDIR /admin-ui

COPY admin-ui/package*.json ./
RUN npm ci

COPY admin-ui/ ./
RUN npm run build

FROM python:3.11-slim

LABEL maintainer="anyrouter2proxy"
LABEL version="3.0.0"
LABEL description="AnyRouter2Proxy - Anthropic/OpenAI Protocol Proxy (Node.js SDK Mode)"

WORKDIR /app

RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/

COPY anyrouter2anthropic.py .
COPY anyrouter2openai.py .
COPY codex_anyrouter_proxy.py .
COPY --from=admin-ui-build /admin-static ./admin-static

RUN mkdir -p /app/config \
    && useradd -m -u 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

# 9996: Codex Responses API 代理端口
# 9998: Anthropic 代理端口
# 9999: OpenAI 代理端口
EXPOSE 9996 9998 9999

ENV PYTHONUNBUFFERED=1
ENV HOST=0.0.0.0
ENV ENV_FILE_PATH=/app/config/.env

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD if [ "$RUN_MODE" = "codex" ]; then port=${CODEX_PROXY_PORT:-9996}; elif [ "$RUN_MODE" = "openai" ]; then port=${OPENAI_PROXY_PORT:-9999}; else port=${PORT:-9998}; fi; curl -f http://localhost:${port}/health || exit 1

CMD ["sh", "-c", "if [ \"$RUN_MODE\" = \"anthropic\" ]; then python3 anyrouter2anthropic.py; elif [ \"$RUN_MODE\" = \"openai\" ]; then python3 anyrouter2openai.py; elif [ \"$RUN_MODE\" = \"codex\" ]; then python3 codex_anyrouter_proxy.py; else echo 'Please set RUN_MODE to \"anthropic\", \"openai\", or \"codex\"'; exit 1; fi"]
