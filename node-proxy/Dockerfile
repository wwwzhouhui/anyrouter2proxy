FROM node:20-slim

LABEL maintainer="anyrouter2proxy"
LABEL description="AnyRouter Node.js Proxy - Anthropic SDK WAF bypass"

WORKDIR /app

RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY package.json package-lock.json ./
RUN npm ci --omit=dev

COPY server.mjs .

RUN chown -R node:node /app
USER node

EXPOSE 4000

ENV NODE_ENV=production

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${NODE_PROXY_PORT:-4000}/health || exit 1

CMD ["node", "server.mjs"]
