FROM python:3.11-slim

# 设置维护者信息
LABEL maintainer="anyrouter2proxy"
LABEL version="2.0.0"
LABEL description="AnyRouter2Proxy - Anthropic/OpenAI Protocol Proxy (Passthrough Mode)"

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/

# 复制应用文件
COPY anyrouter2anthropic.py .
COPY anyrouter2openai.py .

# 创建非root用户
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# 暴露端口
# 9998: Anthropic 代理端口
# 9999: OpenAI 代理端口
EXPOSE 9998 9999

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV HOST=0.0.0.0

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:9998/health || exit 1

# 启动命令 - 使用 exec form 以便信号正确传递
# 可以通过环境变量选择运行哪个服务
CMD ["sh", "-c", "if [ \"$RUN_MODE\" = \"anthropic\" ]; then python3 anyrouter2anthropic.py; elif [ \"$RUN_MODE\" = \"openai\" ]; then python3 anyrouter2openai.py; else echo 'Please set RUN_MODE environment variable to \"anthropic\" or \"openai\"'; fi"]
