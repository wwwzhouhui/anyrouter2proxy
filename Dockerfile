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

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# 9998: Anthropic 代理端口
# 9999: OpenAI 代理端口
EXPOSE 9998 9999

ENV PYTHONUNBUFFERED=1
ENV HOST=0.0.0.0

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT:-9998}/health || exit 1

CMD ["sh", "-c", "if [ \"$RUN_MODE\" = \"anthropic\" ]; then python3 anyrouter2anthropic.py; elif [ \"$RUN_MODE\" = \"openai\" ]; then python3 anyrouter2openai.py; else echo 'Please set RUN_MODE to \"anthropic\" or \"openai\"'; exit 1; fi"]
