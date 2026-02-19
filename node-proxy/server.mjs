/**
 * AnyRouter Node.js Proxy
 *
 * 使用官方 Anthropic Node.js SDK 转发请求，并处理 WAF 挑战。
 *
 * 启动方式：
 *   cd node-proxy
 *   npm install
 *   npm start
 */

import Anthropic from '@anthropic-ai/sdk';
import crypto from 'crypto';
import http from 'http';
import https from 'https';
import zlib from 'zlib';
import { CookieJar } from 'tough-cookie';

const PORT = process.env.NODE_PROXY_PORT || 4000;
const ANTHROPIC_BASE_URL = process.env.ANYROUTER_BASE_URL || 'https://anyrouter.top';

/**
 * 生成随机十六进制字符串
 */
function randomHex(length) {
  return crypto.randomBytes(Math.ceil(length / 2)).toString('hex').slice(0, length);
}

// 全局 Cookie Jar，用于存储 WAF cookie
const cookieJar = new CookieJar();

/**
 * 解析请求体
 */
function parseBody(req) {
  return new Promise((resolve, reject) => {
    let body = '';
    req.on('data', chunk => body += chunk);
    req.on('end', () => {
      try {
        resolve(JSON.parse(body));
      } catch (e) {
        reject(e);
      }
    });
    req.on('error', reject);
  });
}

/**
 * 从请求头提取 API Key
 */
function extractApiKey(headers) {
  if (headers['x-api-key']) {
    return headers['x-api-key'];
  }
  const auth = headers['authorization'] || '';
  if (auth.toLowerCase().startsWith('bearer ')) {
    return auth.slice(7);
  }
  return null;
}

/**
 * 解析 WAF 挑战并计算 cookie 值
 */
function solveWafChallenge(html) {
  // 提取 arg1
  const arg1Match = html.match(/var\s+arg1\s*=\s*'([0-9A-Fa-f]+)'/);
  if (!arg1Match) {
    console.log('WAF challenge: arg1 not found');
    return null;
  }
  const arg1 = arg1Match[1];
  console.log('WAF challenge detected, arg1:', arg1);

  // ACW WAF 挑战的解密逻辑
  // 位置映射数组（从混淆代码中提取的标准值）
  const m = [15, 35, 29, 24, 33, 16, 1, 38, 10, 9, 19, 31, 40, 27, 22, 23, 25, 13, 6, 11, 39, 18, 20, 8, 14, 21, 32, 26, 2, 30, 7, 4, 17, 5, 3, 28, 34, 37, 12, 36];

  // XOR key（这是标准 ACW 挑战使用的固定值）
  const p = '3000176000856006061501533003690027800375';

  // 根据位置映射重排 arg1 字符
  const q = [];
  for (let x = 0; x < arg1.length; x++) {
    const y = arg1[x];
    for (let z = 0; z < m.length; z++) {
      if (m[z] === x + 1) {
        q[z] = y;
      }
    }
  }

  const u = q.join('');

  // XOR 运算生成最终 cookie 值
  let v = '';
  for (let x = 0; x < u.length && x < p.length; x += 2) {
    const a = parseInt(u.substring(x, x + 2), 16) ^ parseInt(p.substring(x, x + 2), 16);
    let hex = a.toString(16);
    if (hex.length === 1) {
      hex = '0' + hex;
    }
    v += hex;
  }

  console.log('WAF challenge solved, cookie value:', v);
  return v;
}

/**
 * 检测响应是否是 WAF 挑战页面
 */
function isWafChallenge(text) {
  return typeof text === 'string' && text.includes('acw_sc__v2') && text.includes('arg1');
}

/**
 * 使用原生 HTTPS 发送请求（带 cookie 支持和 gzip 解压）
 */
async function makeRawRequest(url, options, body) {
  return new Promise((resolve, reject) => {
    const urlObj = new URL(url);

    // 从 cookie jar 获取 cookies
    const cookies = cookieJar.getCookieStringSync(url);

    const reqOptions = {
      hostname: urlObj.hostname,
      port: urlObj.port || 443,
      path: urlObj.pathname,
      method: options.method || 'POST',
      headers: {
        'Accept-Encoding': 'identity',  // 禁用压缩，方便调试
        ...options.headers,
        'Host': urlObj.hostname,
        'Cookie': cookies || undefined,
      }
    };

    // 删除空的 Cookie header
    if (!reqOptions.headers['Cookie']) {
      delete reqOptions.headers['Cookie'];
    }

    console.log('Making request to:', url);
    console.log('Request headers:', JSON.stringify(reqOptions.headers, null, 2));

    const req = https.request(reqOptions, (res) => {
      const chunks = [];

      // 根据编码选择解压方式
      let stream = res;
      const encoding = res.headers['content-encoding'];

      console.log('Response encoding:', encoding);

      if (encoding === 'gzip') {
        console.log('Decompressing gzip...');
        stream = res.pipe(zlib.createGunzip());
      } else if (encoding === 'deflate') {
        console.log('Decompressing deflate...');
        stream = res.pipe(zlib.createInflate());
      } else if (encoding === 'br') {
        console.log('Decompressing brotli...');
        stream = res.pipe(zlib.createBrotliDecompress());
      }

      stream.on('data', chunk => {
        chunks.push(chunk);
      });

      stream.on('end', () => {
        const data = Buffer.concat(chunks).toString('utf8');

        console.log('Response status:', res.statusCode);
        console.log('Response content-type:', res.headers['content-type']);
        console.log('Response length:', data.length);
        console.log('Response preview:', data.substring(0, 500));

        // 保存响应中的 cookies
        const setCookies = res.headers['set-cookie'];
        if (setCookies) {
          console.log('Set-Cookie headers:', setCookies);
          for (const cookie of setCookies) {
            try {
              cookieJar.setCookieSync(cookie, url);
            } catch (e) {
              console.log('Cookie parse error:', e.message);
            }
          }
        }

        resolve({
          status: res.statusCode,
          headers: res.headers,
          text: data,
          json: () => {
            try {
              return JSON.parse(data);
            } catch (e) {
              return data;
            }
          }
        });
      });

      stream.on('error', (err) => {
        console.error('Stream decompression error:', err);
        // 如果解压失败，尝试直接读取原始数据
        const rawData = Buffer.concat(chunks).toString('utf8');
        console.log('Raw data preview:', rawData.substring(0, 200));
        reject(err);
      });
    });

    req.on('error', (err) => {
      console.error('Request error:', err);
      reject(err);
    });

    if (body) {
      const bodyStr = typeof body === 'string' ? body : JSON.stringify(body);
      console.log('Request body preview:', bodyStr.substring(0, 200));
      req.write(bodyStr);
    }
    req.end();
  });
}

/**
 * 处理 WAF 并获取有效响应
 */
async function fetchWithWafHandling(url, options, body, maxRetries = 3) {
  for (let attempt = 0; attempt < maxRetries; attempt++) {
    const response = await makeRawRequest(url, options, body);

    // 检查是否是 WAF 挑战
    if (response.status === 200 && isWafChallenge(response.text)) {
      console.log(`WAF challenge detected (attempt ${attempt + 1}/${maxRetries})`);

      const cookieValue = solveWafChallenge(response.text);
      if (cookieValue) {
        // 设置解决后的 cookie
        const expires = new Date(Date.now() + 3600000).toUTCString();
        const cookieStr = `acw_sc__v2=${cookieValue}; expires=${expires}; path=/`;
        cookieJar.setCookieSync(cookieStr, url);
        console.log('WAF cookie set, retrying request...');
        continue;
      } else {
        console.log('Failed to solve WAF challenge');
        return response;
      }
    }

    return response;
  }

  throw new Error('Max retries exceeded for WAF challenge');
}

/**
 * 创建带 WAF 处理的自定义 fetch
 */
function createWafAwareFetch() {
  return async (url, init) => {
    const response = await fetchWithWafHandling(
      url,
      {
        method: init?.method || 'POST',
        headers: init?.headers || {},
      },
      init?.body
    );

    // 返回类似 fetch Response 的对象
    return {
      ok: response.status >= 200 && response.status < 300,
      status: response.status,
      headers: new Map(Object.entries(response.headers)),
      text: async () => response.text,
      json: async () => response.json(),
      body: createReadableStream(response.text),
    };
  };
}

/**
 * 创建可读流
 */
function createReadableStream(text) {
  const encoder = new TextEncoder();
  const data = encoder.encode(text);
  let position = 0;

  return new ReadableStream({
    pull(controller) {
      if (position < data.length) {
        controller.enqueue(data.slice(position));
        position = data.length;
      } else {
        controller.close();
      }
    }
  });
}

/**
 * 判断模型是否支持 thinking（adaptive 类型）
 * 不支持的模型：haiku 系列、3.5 系列
 */
function supportsThinking(model) {
  // haiku 系列不支持 adaptive thinking
  if (/haiku/.test(model)) return false;
  // 3.5 系列不支持 thinking
  if (/claude-3-5-/.test(model)) return false;
  // 其余模型（opus-4-6, sonnet-4-6, sonnet-4-5, opus-4-5, 3-7-sonnet 等）支持
  return true;
}

/**
 * 直接使用 HTTPS 调用 API（绕过 SDK 的限制）
 */
async function callAnthropicApi(apiKey, body, isStream, clientHeaders = {}) {
  const url = `${ANTHROPIC_BASE_URL}/v1/messages`;

  const model = body.model || '';

  // 根据模型能力注入 thinking 字段（Claude Code 对所有支持 thinking 的模型统一用 adaptive）
  if (!body.thinking) {
    if (supportsThinking(model)) {
      body.thinking = { type: 'adaptive' };
    }
    // haiku、3.5 系列等不支持 thinking 的模型不注入
  }
  if (!body.metadata) {
    body.metadata = { user_id: `user_${randomHex(64)}_account__session_${crypto.randomUUID()}` };
  }
  if (!body.max_tokens) {
    if (supportsThinking(model)) {
      body.max_tokens = 16000;
    } else {
      body.max_tokens = 8192;
    }
  }
  // 注入 Claude Code 系统提示（anyrouter 验证请求体必须包含此特征）
  if (!body.system) {
    body.system = [
      {
        type: 'text',
        text: 'You are Claude Code, Anthropic\'s official CLI for Claude.',
        cache_control: { type: 'ephemeral' }
      },
      {
        type: 'text',
        text: `You are an interactive CLI tool that helps users with software engineering tasks. Use the instructions below and the tools available to you to assist the user.

# Tone and style
- Only use emojis if the user explicitly requests it. Avoid using emojis in all communication unless asked.
- Your output will be displayed on a command line interface. Your responses should be short and concise. You can use Github-flavored markdown for formatting, and will be rendered in a monospace font using the CommonMark specification.
- Output text to communicate with the user; all text you output outside of tool use is displayed to the user. Only use tools to complete tasks. Never use tools like Bash or code comments as means to communicate with the user during the session.

# Doing tasks
The user will primarily request you perform software engineering tasks. This includes solving bugs, adding new functionality, refactoring code, explaining code, and more.

Here is useful information about the environment you are running in:
<env>
Platform: ${process.platform}
Shell: bash
</env>`,
        cache_control: { type: 'ephemeral' }
      }
    ];
  }

  const bodyStr = JSON.stringify(body);

  // 需要跳过的 hop-by-hop 头和内部头
  const skipHeaders = new Set([
    'host', 'content-length', 'transfer-encoding', 'connection',
    'keep-alive', 'upgrade', 'accept-encoding',
  ]);

  // 先从客户端头开始，透传所有特殊头（如 Claude Code 的头）
  const headers = {};
  for (const [key, val] of Object.entries(clientHeaders)) {
    if (!skipHeaders.has(key.toLowerCase())) {
      headers[key] = val;
    }
  }

  // 覆盖/补充关键字段
  headers['Content-Type'] = 'application/json';
  delete headers['content-type'];  // 删除小写的，避免重复
  headers['Content-Length'] = Buffer.byteLength(bodyStr);
  headers['x-api-key'] = apiKey;
  headers['Accept'] = isStream ? 'text/event-stream' : 'application/json';
  delete headers['accept'];  // 删除小写的 accept，避免与 Accept 重复

  // 强制覆盖 User-Agent 为 Claude Code（不论客户端传了什么）
  delete headers['user-agent'];
  headers['User-Agent'] = 'claude-cli/2.1.39 (external, cli)';
  if (!headers['anthropic-version']) {
    headers['anthropic-version'] = '2023-06-01';
  }
  if (!headers['anthropic-beta']) {
    const betaFlags = ['claude-code-20250219', 'prompt-caching-scope-2026-01-05', 'effort-2025-11-24'];
    // 只对支持 thinking 的模型添加 adaptive-thinking beta 标记
    if (supportsThinking(model)) {
      betaFlags.push('adaptive-thinking-2026-01-28');
    }
    headers['anthropic-beta'] = betaFlags.join(',');
  }
  if (!headers['x-app']) {
    headers['x-app'] = 'cli';
  }
  if (!headers['anthropic-dangerous-direct-browser-access']) {
    headers['anthropic-dangerous-direct-browser-access'] = 'true';
  }
  if (!headers['claude-code-attribution-header']) {
    headers['claude-code-attribution-header'] = '0';
  }
  if (!headers['claude-code-disable-nonessential-traffic']) {
    headers['claude-code-disable-nonessential-traffic'] = '1';
  }
  // x-stainless SDK 指纹头
  if (!headers['x-stainless-lang']) {
    headers['x-stainless-lang'] = 'js';
    headers['x-stainless-package-version'] = '0.73.0';
    headers['x-stainless-os'] = 'Windows';
    headers['x-stainless-arch'] = 'x64';
    headers['x-stainless-runtime'] = 'node';
    headers['x-stainless-runtime-version'] = process.version;
    headers['x-stainless-retry-count'] = '0';
    headers['x-stainless-timeout'] = '600';
  }
  if (!headers['sec-fetch-mode']) {
    headers['sec-fetch-mode'] = 'cors';
  }
  if (!headers['accept-language']) {
    headers['accept-language'] = '*';
  }

  // 移除 authorization 避免冲突
  delete headers['authorization'];

  console.log('[转发头]', JSON.stringify(
    Object.fromEntries(Object.entries(headers).filter(([k]) => k.toLowerCase() !== 'x-api-key')),
    null, 2
  ));

  const response = await fetchWithWafHandling(url, { method: 'POST', headers }, bodyStr);

  return response;
}

/**
 * 处理 /v1/messages 请求
 */
async function handleMessages(req, res, body) {
  const apiKey = extractApiKey(req.headers);
  if (!apiKey) {
    res.writeHead(401, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: { type: 'authentication_error', message: 'API key required' } }));
    return;
  }

  const isStream = body.stream === true;
  let headersSent = false;

  console.log(`[${new Date().toISOString()}] ${body.model} stream=${isStream} key=${apiKey.substring(0, 10)}...`);

  try {
    const response = await callAnthropicApi(apiKey, body, isStream, req.headers);

    // 检查响应是否仍然是 WAF 页面
    if (isWafChallenge(response.text)) {
      console.error('Failed to bypass WAF after retries');
      res.writeHead(503, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({
        type: 'error',
        error: {
          type: 'waf_error',
          message: 'Failed to bypass WAF protection. Please try again later.',
        }
      }));
      return;
    }

    if (isStream) {
      // 流式响应
      res.writeHead(200, {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        'X-Accel-Buffering': 'no',
      });
      headersSent = true;

      // 解析 SSE 事件并转发
      const lines = response.text.split('\n');
      for (const line of lines) {
        if (line.trim()) {
          res.write(line + '\n');
        } else {
          res.write('\n');
        }
      }
      res.end();

    } else {
      // 非流式响应
      const contentType = response.headers['content-type'] || 'application/json';

      if (contentType.includes('application/json')) {
        res.writeHead(response.status, { 'Content-Type': 'application/json' });
        res.end(response.text);
      } else {
        // 可能还是 HTML（错误页面）
        console.error('Unexpected content type:', contentType);
        console.error('Response preview:', response.text.substring(0, 500));
        res.writeHead(502, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({
          type: 'error',
          error: {
            type: 'upstream_error',
            message: 'Unexpected response from upstream',
          }
        }));
      }
    }

  } catch (error) {
    console.error('API Error:', error);

    if (!headersSent && !res.headersSent) {
      const statusCode = error.status || 500;
      res.writeHead(statusCode, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({
        type: 'error',
        error: {
          type: error.type || 'api_error',
          message: error.message,
        }
      }));
    } else {
      res.write(`event: error\ndata: ${JSON.stringify({ type: 'error', error: { type: 'api_error', message: error.message } })}\n\n`);
      res.end();
    }
  }
}

/**
 * 处理健康检查
 */
function handleHealth(req, res) {
  res.writeHead(200, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify({
    status: 'ok',
    mode: 'node-proxy-waf-bypass',
    upstream: ANTHROPIC_BASE_URL,
    cookies: cookieJar.getCookieStringSync(ANTHROPIC_BASE_URL) ? 'present' : 'none'
  }));
}

/**
 * 主服务器
 */
const server = http.createServer(async (req, res) => {
  // CORS 支持
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization, x-api-key, anthropic-version, anthropic-beta, claude-code-attribution-header, claude-code-disable-nonessential-traffic');

  if (req.method === 'OPTIONS') {
    res.writeHead(204);
    res.end();
    return;
  }

  const url = new URL(req.url, `http://localhost:${PORT}`);

  try {
    if (url.pathname === '/v1/messages' && req.method === 'POST') {
      const body = await parseBody(req);
      await handleMessages(req, res, body);
    } else if (url.pathname === '/health' && req.method === 'GET') {
      handleHealth(req, res);
    } else if (url.pathname === '/' && req.method === 'GET') {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({
        service: 'AnyRouter Node.js Proxy',
        mode: 'waf-bypass',
        upstream: ANTHROPIC_BASE_URL,
        description: 'Proxy with WAF challenge solver',
      }));
    } else {
      res.writeHead(404, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: 'Not Found' }));
    }
  } catch (error) {
    console.error('Server Error:', error);
    if (!res.headersSent) {
      res.writeHead(500, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: error.message }));
    }
  }
});

server.listen(PORT, () => {
  console.log(`
╔══════════════════════════════════════════════════════════╗
║      AnyRouter Node.js Proxy (WAF Bypass Mode)           ║
╠══════════════════════════════════════════════════════════╣
║  代理地址: http://0.0.0.0:${PORT}
║  上游服务: ${ANTHROPIC_BASE_URL}
╠══════════════════════════════════════════════════════════╣
║  功能: 自动处理 ACW WAF JavaScript 挑战                   ║
╠══════════════════════════════════════════════════════════╣
║  端点:                                                    ║
║    POST /v1/messages - Anthropic Messages API            ║
║    GET  /health      - 健康检查                           ║
╚══════════════════════════════════════════════════════════╝
`);
});
