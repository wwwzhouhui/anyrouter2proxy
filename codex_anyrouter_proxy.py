"""
Codex AnyRouter proxy.

This service exposes an OpenAI-compatible /v1 proxy for Codex's
`wire_api = "responses"` mode and forwards requests to AnyRouter's
OpenAI-compatible endpoint.

Flow:
  Codex -> this proxy (9996) -> https://anyrouter.top/v1
"""

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

DEFAULT_UPSTREAM_BASE_URL = "https://anyrouter.top/v1"
DEFAULT_CODEX_PROXY_MODEL = "gpt-5.5"
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "changeme"
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "300"))
ADMIN_TOKEN_TTL_SECONDS = int(os.getenv("ADMIN_TOKEN_TTL_SECONDS", "86400"))
ADMIN_TOKEN_SECRET = os.getenv("ADMIN_TOKEN_SECRET") or secrets.token_urlsafe(32)
ADMIN_STATIC_DIR = Path(__file__).resolve().parent / "admin-static"

CREATE_ENDPOINTS_WITH_MODEL = {
    "responses",
    "chat/completions",
    "embeddings",
}

HOP_BY_HOP_HEADERS = {
    "host",
    "content-length",
    "transfer-encoding",
    "connection",
    "keep-alive",
    "upgrade",
    "proxy-authorization",
    "proxy-connection",
    "accept-encoding",
}

RESPONSE_SKIP_HEADERS = {
    "content-length",
    "transfer-encoding",
    "connection",
    "content-encoding",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "trailer",
    "upgrade",
}

CODEX_COMPAT_INSTRUCTIONS = """You are Codex, a coding agent based on GPT-5. You are running in a local API compatibility proxy. Answer the user's request directly and keep responses concise unless more detail is useful."""


def _str_to_bool(value: str) -> bool:
    return value.strip().lower() in ("true", "1", "yes", "on")


class EnvFile:
    """Small .env reader/writer used by the admin UI."""

    def __init__(self, path: str | None = None):
        self.path = Path(path or os.getenv("ENV_FILE_PATH", Path(__file__).resolve().parent / ".env"))

    def exists(self) -> bool:
        return self.path.is_file()

    def read(self) -> dict[str, str]:
        result: dict[str, str] = {}
        if not self.exists():
            return result
        for raw_line in self.path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("'\"")
            if key:
                result[key] = value
        return result

    def set_many(self, items: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.exists():
            self._backup()
            lines = self.path.read_text(encoding="utf-8").splitlines()
        else:
            lines = []

        updated: set[str] = set()
        new_lines: list[str] = []

        for raw_line in lines:
            stripped = raw_line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key = stripped.split("=", 1)[0].strip()
                if key in items:
                    new_lines.append(f"{key}={items[key]}")
                    updated.add(key)
                    continue
            new_lines.append(raw_line)

        missing = [(key, value) for key, value in items.items() if key not in updated]
        if missing and new_lines and new_lines[-1] != "":
            new_lines.append("")
        for key, value in missing:
            new_lines.append(f"{key}={value}")

        content = "\n".join(new_lines)
        if content and not content.endswith("\n"):
            content += "\n"

        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp_path.write_text(content, encoding="utf-8")
        os.replace(tmp_path, self.path)

    def _backup(self) -> None:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        backup_path = self.path.with_name(f"{self.path.name}.backup.{timestamp}")
        backup_path.write_text(self.path.read_text(encoding="utf-8"), encoding="utf-8")


class RuntimeConfig:
    """Runtime settings shared by the proxy and admin API."""

    def __init__(self, env_file: EnvFile):
        self.env_file = env_file
        self._lock = RLock()
        self.upstream_base_url = DEFAULT_UPSTREAM_BASE_URL
        self.api_keys: list[str] = []
        self.proxy_api_keys: list[str] = []
        self.model = DEFAULT_CODEX_PROXY_MODEL
        self.force_model = False
        self.admin_username = DEFAULT_ADMIN_USERNAME
        self.admin_password = DEFAULT_ADMIN_PASSWORD
        self.has_custom_admin_password = False
        self.load()

    def load(self) -> None:
        env_data = self.env_file.read()

        def setting(key: str, default: str = "") -> str:
            if key in env_data:
                return env_data[key]
            return os.getenv(key, default)

        upstream_base_url = (
            setting("ANYROUTER_OPENAI_BASE_URL")
            or DEFAULT_UPSTREAM_BASE_URL
        ).rstrip("/")
        raw_keys = setting("ANYROUTER_API_KEY")
        raw_proxy_keys = setting("PROXY_API_KEY") or setting("PROXY_API_KEYS")
        model = setting("CODEX_PROXY_MODEL") or DEFAULT_CODEX_PROXY_MODEL
        force_model = _str_to_bool(setting("CODEX_PROXY_FORCE_MODEL", "false"))

        admin_username = setting("ADMIN_USERNAME") or DEFAULT_ADMIN_USERNAME
        raw_admin_password = setting("ADMIN_PASSWORD")
        admin_password = raw_admin_password or DEFAULT_ADMIN_PASSWORD

        with self._lock:
            self.upstream_base_url = upstream_base_url
            self.api_keys = split_api_keys(raw_keys)
            self.proxy_api_keys = split_api_keys(raw_proxy_keys)
            self.model = model.strip() or DEFAULT_CODEX_PROXY_MODEL
            self.force_model = force_model
            self.admin_username = admin_username.strip() or DEFAULT_ADMIN_USERNAME
            self.admin_password = admin_password
            self.has_custom_admin_password = bool(raw_admin_password)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "upstream_base_url": self.upstream_base_url,
                "api_keys": list(self.api_keys),
                "proxy_api_keys": list(self.proxy_api_keys),
                "model": self.model,
                "force_model": self.force_model,
                "admin_username": self.admin_username,
                "has_custom_admin_password": self.has_custom_admin_password,
            }

    def update_settings(self, upstream_base_url: str, model: str, force_model: bool) -> dict[str, Any]:
        upstream_base_url = upstream_base_url.strip().rstrip("/")
        model = model.strip()
        if not upstream_base_url.startswith(("http://", "https://")):
            raise ValueError("上游地址必须以 http:// 或 https:// 开头")
        if not model:
            raise ValueError("默认模型不能为空")

        self.env_file.set_many(
            {
                "ANYROUTER_OPENAI_BASE_URL": upstream_base_url,
                "CODEX_PROXY_MODEL": model,
                "CODEX_PROXY_FORCE_MODEL": "true" if force_model else "false",
            }
        )
        os.environ["ANYROUTER_OPENAI_BASE_URL"] = upstream_base_url
        os.environ["CODEX_PROXY_MODEL"] = model
        os.environ["CODEX_PROXY_FORCE_MODEL"] = "true" if force_model else "false"

        with self._lock:
            self.upstream_base_url = upstream_base_url
            self.model = model
            self.force_model = force_model
        return self.snapshot()

    def update_api_keys(self, keys: list[str]) -> dict[str, Any]:
        clean_keys = [key.strip() for key in keys if key.strip()]
        self.env_file.set_many({"ANYROUTER_API_KEY": ",".join(clean_keys)})
        os.environ["ANYROUTER_API_KEY"] = ",".join(clean_keys)
        with self._lock:
            self.api_keys = clean_keys
        return self.snapshot()

    def update_proxy_api_keys(self, keys: list[str]) -> dict[str, Any]:
        clean_keys = [key.strip() for key in keys if key.strip()]
        self.env_file.set_many({"PROXY_API_KEY": ",".join(clean_keys)})
        os.environ["PROXY_API_KEY"] = ",".join(clean_keys)
        with self._lock:
            self.proxy_api_keys = clean_keys
        return self.snapshot()

    def update_admin_password(self, old_password: str, new_password: str) -> None:
        if not verify_password(old_password, self.admin_password):
            raise ValueError("当前密码不正确")
        if len(new_password) < 8:
            raise ValueError("新密码至少需要 8 个字符")

        self.env_file.set_many({"ADMIN_PASSWORD": new_password})
        os.environ["ADMIN_PASSWORD"] = new_password
        with self._lock:
            self.admin_password = new_password
            self.has_custom_admin_password = True


http_client: httpx.AsyncClient | None = None
api_key_index = 0
api_key_lock = asyncio.Lock()


def get_client() -> httpx.AsyncClient:
    if http_client is None:
        raise RuntimeError("HTTP client not initialized")
    return http_client


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global http_client
    http_client = httpx.AsyncClient(timeout=HTTP_TIMEOUT)
    config = runtime_config.snapshot()
    logger.info("Started: Codex AnyRouter proxy")
    logger.info("Upstream OpenAI base URL: %s", config["upstream_base_url"])
    logger.info("Default model: %s", config["model"])
    yield
    await http_client.aclose()


app = FastAPI(title="Codex AnyRouter Proxy", lifespan=lifespan)
if (ADMIN_STATIC_DIR / "assets").is_dir():
    app.mount("/admin/assets", StaticFiles(directory=ADMIN_STATIC_DIR / "assets"), name="admin-assets")


def split_api_keys(raw_value: str) -> list[str]:
    return [key.strip() for key in raw_value.split(",") if key.strip()]


async def select_api_key(keys: list[str]) -> str | None:
    global api_key_index
    if not keys:
        return None
    if len(keys) == 1:
        return keys[0]

    async with api_key_lock:
        key = keys[api_key_index % len(keys)]
        api_key_index += 1
        return key


runtime_config = RuntimeConfig(EnvFile())


class LoginRequest(BaseModel):
    username: str
    password: str


class SettingsUpdateRequest(BaseModel):
    upstream_base_url: str
    model: str
    force_model: bool = False


class KeysUpdateRequest(BaseModel):
    keys: list[str]


class KeyAddRequest(BaseModel):
    key: str


class PasswordUpdateRequest(BaseModel):
    old_password: str
    new_password: str


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def verify_password(password: str, expected_password: str) -> bool:
    return hmac.compare_digest(hash_password(password), hash_password(expected_password))


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def create_admin_token(username: str) -> str:
    payload = {
        "sub": username,
        "iat": int(time.time()),
        "exp": int(time.time()) + ADMIN_TOKEN_TTL_SECONDS,
    }
    payload_part = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(ADMIN_TOKEN_SECRET.encode("utf-8"), payload_part.encode("ascii"), hashlib.sha256).digest()
    return f"{payload_part}.{_b64url_encode(signature)}"


def verify_admin_token(token: str) -> dict[str, Any] | None:
    try:
        payload_part, signature_part = token.split(".", 1)
        expected_signature = hmac.new(
            ADMIN_TOKEN_SECRET.encode("utf-8"),
            payload_part.encode("ascii"),
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(_b64url_encode(expected_signature), signature_part):
            return None
        payload = json.loads(_b64url_decode(payload_part).decode("utf-8"))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        return payload
    except Exception:
        return None


async def require_admin(request: Request) -> dict[str, Any]:
    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="需要先登录")
    payload = verify_admin_token(auth_header[7:])
    if not payload:
        raise HTTPException(status_code=401, detail="登录已过期或无效")
    return payload


def mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 12:
        return "***"
    return f"{key[:4]}...{key[-4:]}"


def normalize_key_list(values: list[str]) -> list[str]:
    keys: list[str] = []
    for value in values:
        for item in value.replace("\n", ",").split(","):
            item = item.strip()
            if item:
                keys.append(item)
    return keys


def extract_presented_api_keys(request: Request) -> list[str]:
    values: list[str] = []
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        values.extend(split_api_keys(auth_header[7:]))
    x_api_key = request.headers.get("x-api-key", "")
    if x_api_key:
        values.extend(split_api_keys(x_api_key))
    return values


async def validate_proxy_access(request: Request) -> None:
    config = runtime_config.snapshot()
    proxy_keys = config["proxy_api_keys"]
    if not proxy_keys:
        return

    presented_keys = extract_presented_api_keys(request)
    for presented in presented_keys:
        for expected in proxy_keys:
            if hmac.compare_digest(presented, expected):
                return

    raise HTTPException(
        status_code=401,
        detail={
            "error": {
                "type": "authentication_error",
                "message": "代理 API Key 无效。请使用管理端提供的 API Key。",
            }
        },
    )


def build_admin_config() -> dict[str, Any]:
    config = runtime_config.snapshot()
    keys = config["api_keys"]
    proxy_keys = config["proxy_api_keys"]
    return {
        "settings": {
            "upstream_base_url": config["upstream_base_url"],
            "model": config["model"],
            "force_model": config["force_model"],
        },
        "api_keys": {
            "count": len(keys),
            "masked": [mask_key(key) for key in keys],
        },
        "proxy_api_keys": {
            "count": len(proxy_keys),
            "values": proxy_keys,
            "masked": [mask_key(key) for key in proxy_keys],
            "enabled": bool(proxy_keys),
        },
        "admin": {
            "username": config["admin_username"],
            "using_default_password": not config["has_custom_admin_password"],
        },
        "service": {
            "port": int(os.getenv("CODEX_PROXY_PORT", "9996")),
            "env_file": str(runtime_config.env_file.path),
        },
    }


ADMIN_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Codex AnyRouter 管理端</title>
  <style>
    :root {
      --bg: #f5f1e8;
      --panel: #fffdf8;
      --ink: #17201a;
      --muted: #697066;
      --line: #d8d0c0;
      --accent: #0f766e;
      --accent-dark: #115e59;
      --danger: #b42318;
      --ok: #277a3e;
      --shadow: 0 18px 60px rgba(50, 42, 28, 0.14);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      color: var(--ink);
      background:
        linear-gradient(135deg, rgba(15, 118, 110, 0.12), transparent 34%),
        radial-gradient(circle at 88% 12%, rgba(180, 83, 9, 0.14), transparent 30%),
        var(--bg);
      font-family: Georgia, "Times New Roman", serif;
    }
    button, input, textarea { font: inherit; }
    .shell {
      width: min(1160px, calc(100% - 32px));
      margin: 0 auto;
      padding: 34px 0 46px;
    }
    header {
      display: flex;
      justify-content: space-between;
      gap: 18px;
      align-items: flex-end;
      margin-bottom: 24px;
    }
    h1, h2, h3, p { margin: 0; }
    h1 { font-size: clamp(30px, 4vw, 52px); line-height: 1; letter-spacing: 0; }
    .subtitle { color: var(--muted); margin-top: 10px; max-width: 680px; }
    .grid {
      display: grid;
      grid-template-columns: minmax(0, 1.05fr) minmax(340px, 0.95fr);
      gap: 18px;
    }
    .panel {
      background: rgba(255, 253, 248, 0.92);
      border: 1px solid var(--line);
      box-shadow: var(--shadow);
      border-radius: 8px;
      padding: 20px;
    }
    .panel h2 { font-size: 22px; margin-bottom: 14px; }
    label { display: block; color: var(--muted); font-size: 14px; margin-bottom: 7px; }
    input, textarea {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--ink);
      padding: 11px 12px;
      outline: none;
    }
    textarea { min-height: 118px; resize: vertical; font-family: Consolas, monospace; }
    input:focus, textarea:focus { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(15, 118, 110, 0.14); }
    .field { margin-bottom: 14px; }
    .row { display: flex; gap: 10px; align-items: center; }
    .row > * { flex: 1; }
    .check {
      display: flex;
      align-items: center;
      gap: 8px;
      color: var(--ink);
      margin: 5px 0 16px;
    }
    .check input { width: 18px; height: 18px; }
    .actions { display: flex; gap: 10px; flex-wrap: wrap; }
    button {
      border: 0;
      border-radius: 6px;
      padding: 10px 14px;
      color: white;
      background: var(--accent);
      cursor: pointer;
    }
    button:hover { background: var(--accent-dark); }
    button.secondary { background: #334155; }
    button.danger { background: var(--danger); }
    button.ghost {
      color: var(--ink);
      background: transparent;
      border: 1px solid var(--line);
    }
    .key-list { display: grid; gap: 8px; margin: 12px 0 16px; }
    .key-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px 12px;
      background: #fff;
      font-family: Consolas, monospace;
      font-size: 14px;
    }
    .status {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 999px;
      padding: 8px 12px;
      color: var(--muted);
      white-space: nowrap;
    }
    .dot { width: 9px; height: 9px; border-radius: 50%; background: var(--ok); }
    .message { margin-top: 12px; color: var(--muted); min-height: 22px; }
    .message.error { color: var(--danger); }
    .message.ok { color: var(--ok); }
    .login {
      max-width: 430px;
      margin: 11vh auto 0;
    }
    .hidden { display: none !important; }
    .meta {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
      margin-bottom: 16px;
    }
    .metric {
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 12px;
      background: #fff;
    }
    .metric strong { display: block; font-size: 22px; margin-top: 5px; }
    code {
      background: rgba(15, 118, 110, 0.1);
      border-radius: 4px;
      padding: 2px 5px;
      word-break: break-all;
    }
    @media (max-width: 860px) {
      header { align-items: flex-start; flex-direction: column; }
      .grid { grid-template-columns: 1fr; }
      .row { flex-direction: column; align-items: stretch; }
      .meta { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <main class="shell">
    <section id="loginView" class="panel login">
      <h1>管理登录</h1>
      <p class="subtitle">管理 Codex AnyRouter 的上游配置、模型和多账号 API Key。</p>
      <div class="field" style="margin-top:20px">
        <label for="loginUser">用户名</label>
        <input id="loginUser" autocomplete="username" value="admin">
      </div>
      <div class="field">
        <label for="loginPassword">密码</label>
        <input id="loginPassword" autocomplete="current-password" type="password" value="">
      </div>
      <div class="actions">
        <button id="loginButton">登录</button>
      </div>
      <p id="loginMessage" class="message"></p>
    </section>

    <section id="dashboardView" class="hidden">
      <header>
        <div>
          <h1>Codex AnyRouter</h1>
          <p class="subtitle">用于管理本地 <code>/v1/responses</code> 转发、上游模型和多账号轮询。</p>
        </div>
        <div class="status"><span class="dot"></span><span id="serviceStatus">已连接</span></div>
      </header>

      <div class="grid">
        <section class="panel">
          <h2>运行配置</h2>
          <div class="meta">
            <div class="metric"><span>已配置 Key 数</span><strong id="keyCount">0</strong></div>
            <div class="metric"><span>管理员</span><strong id="adminUser">admin</strong></div>
          </div>
          <div class="field">
            <label for="baseUrl">AnyRouter OpenAI 兼容地址</label>
            <input id="baseUrl" placeholder="https://anyrouter.top/v1">
          </div>
          <div class="field">
            <label for="model">默认模型</label>
            <input id="model" placeholder="gpt-5.5">
          </div>
          <label class="check"><input id="forceModel" type="checkbox"> 强制所有请求使用默认模型</label>
          <div class="actions">
            <button id="saveSettings">保存配置</button>
            <button class="secondary" id="reloadConfig">从 .env 重载</button>
            <button class="ghost" id="logoutButton">退出登录</button>
          </div>
          <p id="settingsMessage" class="message"></p>
        </section>

        <section class="panel">
          <h2>第三方平台接入</h2>
          <p class="subtitle">CherryStudio、sub2api 等平台填写下面的地址和代理 API Key。</p>
          <div class="field" style="margin-top:14px">
            <label for="clientBaseUrl">请求地址 / Base URL</label>
            <div class="row">
              <input id="clientBaseUrl" readonly>
              <button id="copyBaseUrl">复制</button>
            </div>
          </div>
          <div class="field">
            <label>代理 API Key</label>
            <div id="proxyKeyList" class="key-list"></div>
          </div>
          <div class="actions">
            <button id="generateProxyKey">生成代理 Key</button>
          </div>
          <div class="field" style="margin-top:14px">
            <label for="newProxyKey">添加自定义代理 Key</label>
            <div class="row">
              <input id="newProxyKey" placeholder="sk-proxy-...">
              <button id="addProxyKey">添加</button>
            </div>
          </div>
          <p class="subtitle">第三方平台模型名填写 <code>gpt-5.5</code>，请求格式选择 OpenAI 兼容；代理会自动把 `/v1/chat/completions` 转到上游 `/v1/responses`。</p>
          <p id="proxyKeysMessage" class="message"></p>
        </section>

        <section class="panel">
          <h2>AnyRouter API Key</h2>
          <div id="keyList" class="key-list"></div>
          <div class="field">
            <label for="newKey">添加单个 Key</label>
            <div class="row">
              <input id="newKey" placeholder="sk-...">
              <button id="addKey">添加</button>
            </div>
          </div>
          <div class="field">
            <label for="replaceKeys">批量替换所有 Key</label>
            <textarea id="replaceKeys" placeholder="每行一个 Key，也可以用英文逗号分隔"></textarea>
          </div>
          <div class="actions">
            <button id="replaceAllKeys">替换 Key 列表</button>
          </div>
          <p id="keysMessage" class="message"></p>
        </section>

        <section class="panel">
          <h2>Codex 配置</h2>
          <p class="subtitle">将 Codex 指向这个本地代理：</p>
          <pre><code>[model_providers.custom]
name = "custom"
wire_api = "responses"
requires_openai_auth = true
base_url = "http://127.0.0.1:9996/v1"</code></pre>
        </section>

        <section class="panel">
          <h2>管理密码</h2>
          <div id="defaultPasswordWarning" class="message error hidden">当前仍在使用默认密码。请在暴露服务前修改密码。</div>
          <div class="field">
            <label for="oldPassword">当前密码</label>
            <input id="oldPassword" type="password">
          </div>
          <div class="field">
            <label for="newPassword">新密码</label>
            <input id="newPassword" type="password">
          </div>
          <button id="changePassword">修改密码</button>
          <p id="passwordMessage" class="message"></p>
        </section>
      </div>
    </section>
  </main>

  <script>
    const tokenKey = "codex-anyrouter-admin-token";
    const $ = (id) => document.getElementById(id);

    function token() { return localStorage.getItem(tokenKey) || ""; }
    function setMessage(id, text, kind = "") {
      const el = $(id);
      el.textContent = text || "";
      el.className = `message ${kind}`;
    }
    async function copyText(value, messageId) {
      try {
        await navigator.clipboard.writeText(value);
        setMessage(messageId, "已复制。", "ok");
      } catch (_) {
        setMessage(messageId, "复制失败，请手动选择文本复制。", "error");
      }
    }
    async function api(path, options = {}) {
      const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
      if (token()) headers.Authorization = `Bearer ${token()}`;
      const res = await fetch(path, { ...options, headers });
      if (!res.ok) {
        let detail = res.statusText;
        try {
          const data = await res.json();
          detail = data.detail || data.error?.message || detail;
        } catch (_) {}
        throw new Error(detail);
      }
      return res.json();
    }
    function showDashboard(show) {
      $("loginView").classList.toggle("hidden", show);
      $("dashboardView").classList.toggle("hidden", !show);
    }
    function renderConfig(config) {
      $("baseUrl").value = config.settings.upstream_base_url;
      $("model").value = config.settings.model;
      $("forceModel").checked = Boolean(config.settings.force_model);
      $("clientBaseUrl").value = `${window.location.origin}/v1`;
      $("keyCount").textContent = config.api_keys.count;
      $("adminUser").textContent = config.admin.username;
      $("defaultPasswordWarning").classList.toggle("hidden", !config.admin.using_default_password);
      const proxyList = $("proxyKeyList");
      proxyList.innerHTML = "";
      if (!config.proxy_api_keys.values.length) {
        proxyList.innerHTML = "<p class='message'>当前没有启用代理 Key。启用后第三方平台必须使用这里的 Key 调用。</p>";
      } else {
        config.proxy_api_keys.values.forEach((key, index) => {
          const row = document.createElement("div");
          row.className = "key-item";
          row.innerHTML = `<span>${index + 1}. ${key}</span><span class="actions"><button class="secondary" data-copy-proxy="${index}">复制</button><button class="danger" data-delete-proxy="${index}">删除</button></span>`;
          proxyList.appendChild(row);
        });
      }
      const list = $("keyList");
      list.innerHTML = "";
      if (!config.api_keys.masked.length) {
        list.innerHTML = "<p class='message'>当前没有配置服务端 Key，将透传客户端 Authorization。</p>";
      } else {
        config.api_keys.masked.forEach((key, index) => {
          const row = document.createElement("div");
          row.className = "key-item";
          row.innerHTML = `<span>${index + 1}. ${key}</span><button class="danger" data-index="${index}">删除</button>`;
          list.appendChild(row);
        });
      }
    }
    async function loadConfig() {
      const config = await api("/admin/api/config");
      renderConfig(config);
      showDashboard(true);
    }
    $("loginButton").onclick = async () => {
      try {
        const data = await api("/admin/api/login", {
          method: "POST",
          body: JSON.stringify({ username: $("loginUser").value, password: $("loginPassword").value }),
        });
        localStorage.setItem(tokenKey, data.token);
        setMessage("loginMessage", "");
        await loadConfig();
      } catch (err) {
        setMessage("loginMessage", err.message, "error");
      }
    };
    $("logoutButton").onclick = () => {
      localStorage.removeItem(tokenKey);
      showDashboard(false);
    };
    $("saveSettings").onclick = async () => {
      try {
        await api("/admin/api/settings", {
          method: "PUT",
          body: JSON.stringify({
            upstream_base_url: $("baseUrl").value,
            model: $("model").value,
            force_model: $("forceModel").checked,
          }),
        });
        setMessage("settingsMessage", "配置已保存。", "ok");
        await loadConfig();
      } catch (err) {
        setMessage("settingsMessage", err.message, "error");
      }
    };
    $("reloadConfig").onclick = async () => {
      try {
        await api("/admin/api/reload", { method: "POST" });
        setMessage("settingsMessage", "已从 .env 重载配置。", "ok");
        await loadConfig();
      } catch (err) {
        setMessage("settingsMessage", err.message, "error");
      }
    };
    $("copyBaseUrl").onclick = async () => {
      await copyText($("clientBaseUrl").value, "proxyKeysMessage");
    };
    $("generateProxyKey").onclick = async () => {
      try {
        const data = await api("/admin/api/proxy-keys/generate", { method: "POST" });
        setMessage("proxyKeysMessage", `代理 Key 已生成：${data.key}`, "ok");
        await loadConfig();
      } catch (err) {
        setMessage("proxyKeysMessage", err.message, "error");
      }
    };
    $("addProxyKey").onclick = async () => {
      try {
        await api("/admin/api/proxy-keys", {
          method: "POST",
          body: JSON.stringify({ key: $("newProxyKey").value }),
        });
        $("newProxyKey").value = "";
        setMessage("proxyKeysMessage", "代理 Key 已添加。", "ok");
        await loadConfig();
      } catch (err) {
        setMessage("proxyKeysMessage", err.message, "error");
      }
    };
    $("proxyKeyList").onclick = async (event) => {
      const copyButton = event.target.closest("button[data-copy-proxy]");
      if (copyButton) {
        const rowText = copyButton.closest(".key-item").querySelector("span").textContent;
        await copyText(rowText.replace(/^\\d+\\.\\s*/, ""), "proxyKeysMessage");
        return;
      }
      const deleteButton = event.target.closest("button[data-delete-proxy]");
      if (!deleteButton) return;
      try {
        await api(`/admin/api/proxy-keys/${deleteButton.dataset.deleteProxy}`, { method: "DELETE" });
        setMessage("proxyKeysMessage", "代理 Key 已删除。", "ok");
        await loadConfig();
      } catch (err) {
        setMessage("proxyKeysMessage", err.message, "error");
      }
    };
    $("addKey").onclick = async () => {
      try {
        await api("/admin/api/keys", { method: "POST", body: JSON.stringify({ key: $("newKey").value }) });
        $("newKey").value = "";
        setMessage("keysMessage", "Key 已添加。", "ok");
        await loadConfig();
      } catch (err) {
        setMessage("keysMessage", err.message, "error");
      }
    };
    $("replaceAllKeys").onclick = async () => {
      try {
        await api("/admin/api/keys", {
          method: "PUT",
          body: JSON.stringify({ keys: $("replaceKeys").value.split(/\\n|,/) }),
        });
        $("replaceKeys").value = "";
        setMessage("keysMessage", "Key 列表已替换。", "ok");
        await loadConfig();
      } catch (err) {
        setMessage("keysMessage", err.message, "error");
      }
    };
    $("keyList").onclick = async (event) => {
      const button = event.target.closest("button[data-index]");
      if (!button) return;
      try {
        await api(`/admin/api/keys/${button.dataset.index}`, { method: "DELETE" });
        setMessage("keysMessage", "Key 已删除。", "ok");
        await loadConfig();
      } catch (err) {
        setMessage("keysMessage", err.message, "error");
      }
    };
    $("changePassword").onclick = async () => {
      try {
        await api("/admin/api/password", {
          method: "PUT",
          body: JSON.stringify({ old_password: $("oldPassword").value, new_password: $("newPassword").value }),
        });
        $("oldPassword").value = "";
        $("newPassword").value = "";
        setMessage("passwordMessage", "密码已修改。", "ok");
        await loadConfig();
      } catch (err) {
        setMessage("passwordMessage", err.message, "error");
      }
    };
    if (token()) {
      loadConfig().catch(() => {
        localStorage.removeItem(tokenKey);
        showDashboard(false);
      });
    }
  </script>
</body>
</html>"""


async def resolve_upstream_api_key(request: Request) -> str:
    config = runtime_config.snapshot()
    if config["api_keys"]:
        api_key = await select_api_key(config["api_keys"])
        if api_key:
            return api_key

    if config["proxy_api_keys"]:
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "type": "configuration_error",
                    "message": "已启用代理 API Key，但还没有配置 AnyRouter 上游 API Key。",
                }
            },
        )

    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        api_key = await select_api_key(split_api_keys(auth_header[7:]))
        if api_key:
            return api_key

    x_api_key = request.headers.get("x-api-key", "")
    api_key = await select_api_key(split_api_keys(x_api_key))
    if api_key:
        return api_key

    raise HTTPException(
        status_code=401,
        detail={
            "error": {
                "type": "authentication_error",
                "message": "缺少 API Key。请设置 ANYROUTER_API_KEY，或发送 Authorization: Bearer <key>。",
            }
        },
    )


def build_upstream_headers(request: Request, api_key: str, body_is_json: bool) -> dict[str, str]:
    headers: dict[str, str] = {}
    for key, value in request.headers.items():
        lower_key = key.lower()
        if lower_key in HOP_BY_HOP_HEADERS:
            continue
        if lower_key in ("authorization", "x-api-key"):
            continue
        headers[key] = value

    headers["Authorization"] = f"Bearer {api_key}"
    if body_is_json:
        headers["Content-Type"] = "application/json"
    return headers


def apply_codex_responses_headers(headers: dict[str, str], client_metadata: dict[str, str]) -> dict[str, str]:
    """Add Codex CLI-style fingerprints for AnyRouter's Responses validator."""
    for key in list(headers):
        lower_key = key.lower()
        if lower_key in {
            "user-agent",
            "accept",
            "openai-beta",
            "originator",
            "session-id",
            "thread-id",
            "x-client-request-id",
            "x-codex-beta-features",
            "x-codex-turn-metadata",
            "x-codex-window-id",
        }:
            headers.pop(key, None)

    session_id = client_metadata["session_id"]
    headers["Accept"] = "text/event-stream"
    headers["Originator"] = "Codex Desktop"
    headers["User-Agent"] = "Codex Desktop/0.141.0 (Windows 10.0.19045; x86_64) unknown (codex_exec; 0.141.0)"
    headers["session-id"] = session_id
    headers["thread-id"] = client_metadata["thread_id"]
    headers["x-client-request-id"] = session_id
    headers["x-codex-beta-features"] = "remote_compaction_v2"
    headers["x-codex-turn-metadata"] = client_metadata["x-codex-turn-metadata"]
    headers["x-codex-window-id"] = client_metadata["x-codex-window-id"]
    return headers


def build_upstream_url(base_url: str, upstream_path: str, query_string: str) -> str:
    url = f"{base_url}/{upstream_path.lstrip('/')}"
    if query_string:
        return f"{url}?{query_string}"
    return url


def should_apply_model(upstream_path: str, method: str) -> bool:
    if method.upper() not in ("POST", "PUT", "PATCH"):
        return False
    return upstream_path.strip("/") in CREATE_ENDPOINTS_WITH_MODEL


def maybe_rewrite_json_body(
    upstream_path: str,
    method: str,
    body: bytes,
    model: str,
    force_model: bool,
) -> tuple[bytes, bool]:
    if not body:
        return body, False

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return body, False

    if not isinstance(data, dict):
        return body, True

    if should_apply_model(upstream_path, method):
        if force_model or not data.get("model"):
            data["model"] = model

    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), True


def filter_response_headers(headers: httpx.Headers) -> dict[str, str]:
    return {
        key: value
        for key, value in headers.items()
        if key.lower() not in RESPONSE_SKIP_HEADERS
    }


def normalize_openai_error(value: Any, fallback_message: str = "上游请求失败") -> dict[str, Any]:
    if isinstance(value, bytes):
        return normalize_openai_error(value.decode("utf-8", errors="replace"), fallback_message)

    if isinstance(value, str):
        stripped = value.strip()
        if stripped:
            try:
                return normalize_openai_error(json.loads(stripped), fallback_message)
            except json.JSONDecodeError:
                pass
        return {
            "message": stripped or fallback_message,
            "type": "upstream_error",
            "param": None,
            "code": None,
        }

    if isinstance(value, dict):
        if "error" in value:
            return normalize_openai_error(value["error"], fallback_message)
        message = value.get("message") or value.get("detail") or fallback_message
        return {
            "message": str(message),
            "type": str(value.get("type") or "upstream_error"),
            "param": value.get("param"),
            "code": value.get("code"),
        }

    return {
        "message": fallback_message,
        "type": "upstream_error",
        "param": None,
        "code": None,
    }


def create_error_response(content: Any, status_code: int) -> JSONResponse:
    return JSONResponse(
        {"error": normalize_openai_error(content)},
        status_code=status_code,
    )


def extract_text_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                item_type = item.get("type")
                if item_type in ("text", "input_text", "output_text"):
                    parts.append(str(item.get("text", "")))
                elif item_type == "image_url":
                    image_url = item.get("image_url", {})
                    url = image_url.get("url") if isinstance(image_url, dict) else image_url
                    if url:
                        parts.append(f"[image: {url}]")
        return "\n".join(part for part in parts if part)
    return str(content)


def create_responses_message(role: str, content: str) -> dict[str, Any]:
    content_type = "output_text" if role == "assistant" else "input_text"
    return {
        "type": "message",
        "role": role,
        "content": [
            {
                "type": content_type,
                "text": content,
            }
        ],
    }


def create_codex_client_metadata() -> dict[str, str]:
    session_id = str(uuid.uuid4())
    turn_id = str(uuid.uuid4())
    window_id = f"{session_id}:0"
    installation_id = str(uuid.uuid4())
    turn_metadata = {
        "installation_id": installation_id,
        "session_id": session_id,
        "thread_id": session_id,
        "turn_id": turn_id,
        "window_id": window_id,
        "request_kind": "turn",
        "sandbox": "windows_elevated",
        "turn_started_at_unix_ms": int(time.time() * 1000),
    }
    return {
        "x-codex-installation-id": installation_id,
        "session_id": session_id,
        "thread_id": session_id,
        "x-codex-turn-metadata": json.dumps(turn_metadata, ensure_ascii=False, separators=(",", ":")),
        "x-codex-window-id": window_id,
        "turn_id": turn_id,
    }


def convert_chat_to_responses_request(chat_request: dict[str, Any], model: str) -> dict[str, Any]:
    messages = chat_request.get("messages", [])
    instructions: list[str] = [CODEX_COMPAT_INSTRUCTIONS]
    response_input: list[dict[str, Any]] = []
    client_metadata = create_codex_client_metadata()

    for message in messages:
        if not isinstance(message, dict):
            continue
        role = message.get("role", "user")
        content = extract_text_content(message.get("content", ""))
        if role in ("system", "developer"):
            if content:
                instructions.append(content)
            continue
        if role == "assistant":
            response_input.append(create_responses_message("assistant", content))
        elif role == "tool":
            response_input.append(create_responses_message("user", f"Tool result:\n{content}"))
        else:
            response_input.append(create_responses_message("user", content))

    responses_request: dict[str, Any] = {
        "model": model,
        "input": response_input or [create_responses_message("user", "")],
        "stream": True,
        "instructions": "\n\n".join(instructions),
        "client_metadata": client_metadata,
        "prompt_cache_key": client_metadata["session_id"],
        "store": False,
        "parallel_tool_calls": True,
        "tool_choice": "auto",
        "include": ["reasoning.encrypted_content"],
        "text": {"verbosity": "low"},
    }

    max_tokens = chat_request.get("max_completion_tokens", chat_request.get("max_tokens"))
    if max_tokens is not None:
        responses_request["max_output_tokens"] = max_tokens
    for key in ("temperature", "top_p"):
        if key in chat_request:
            responses_request[key] = chat_request[key]

    reasoning_effort = chat_request.get("reasoning_effort")
    if reasoning_effort:
        responses_request["reasoning"] = {"effort": reasoning_effort, "summary": "auto"}
    elif model.startswith("gpt-5"):
        responses_request["reasoning"] = {"effort": "medium", "summary": "auto"}

    return responses_request


def extract_responses_text(response_json: dict[str, Any]) -> str:
    output_text = response_json.get("output_text")
    if isinstance(output_text, str):
        return output_text

    parts: list[str] = []
    for item in response_json.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if not isinstance(content, dict):
                continue
            if content.get("type") in ("output_text", "text"):
                parts.append(str(content.get("text", "")))
    return "".join(parts)


def convert_responses_usage(response_json: dict[str, Any]) -> dict[str, int]:
    usage = response_json.get("usage") or {}
    input_tokens = int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
    total_tokens = int(usage.get("total_tokens") or input_tokens + output_tokens)
    return {
        "prompt_tokens": input_tokens,
        "completion_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


def create_chat_completion_response(response_json: dict[str, Any], model: str) -> dict[str, Any]:
    finish_reason = "stop" if response_json.get("status") != "cancelled" else "length"
    return {
        "id": f"chatcmpl-{secrets.token_hex(12)}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": extract_responses_text(response_json),
                },
                "finish_reason": finish_reason,
            }
        ],
        "usage": convert_responses_usage(response_json),
    }


def create_chat_stream_chunk(
    request_id: str,
    model: str,
    content: str | None = None,
    role: str | None = None,
    finish_reason: str | None = None,
) -> dict[str, Any]:
    delta: dict[str, str] = {}
    if role is not None:
        delta["role"] = role
    if content is not None:
        delta["content"] = content
    return {
        "id": request_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": delta,
                "finish_reason": finish_reason,
            }
        ],
    }


async def iter_upstream_response(
    response: httpx.Response,
    stream_context: Any,
) -> AsyncGenerator[bytes, None]:
    try:
        async for chunk in response.aiter_bytes():
            if chunk:
                yield chunk
    finally:
        await stream_context.__aexit__(None, None, None)


def should_bridge_chat_completions(upstream_path: str, request_body: dict[str, Any], config: dict[str, Any]) -> bool:
    if upstream_path.strip("/") != "chat/completions":
        return False
    model = request_body.get("model") or config["model"]
    return bool(config["force_model"] or model == config["model"])


async def stream_responses_as_chat_completions(
    responses_request: dict[str, Any],
    upstream_url: str,
    headers: dict[str, str],
    model: str,
) -> AsyncGenerator[str, None]:
    request_id = f"chatcmpl-{secrets.token_hex(12)}"
    yielded_role = False

    try:
        async with get_client().stream("POST", upstream_url, headers=headers, json=responses_request) as resp:
            if resp.status_code != 200:
                error_text = await resp.aread()
                yield f"data: {json.dumps({'error': normalize_openai_error(error_text)}, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
                return

            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data_str = line[6:].strip()
                if not data_str or data_str == "[DONE]":
                    continue
                try:
                    event = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                event_type = event.get("type")
                if event_type in ("response.output_text.delta", "response.refusal.delta"):
                    if not yielded_role:
                        yield f"data: {json.dumps(create_chat_stream_chunk(request_id, model, role='assistant'), ensure_ascii=False)}\n\n"
                        yielded_role = True
                    delta = event.get("delta", "")
                    if delta:
                        yield f"data: {json.dumps(create_chat_stream_chunk(request_id, model, content=delta), ensure_ascii=False)}\n\n"
                elif event_type == "response.error":
                    yield f"data: {json.dumps({'error': normalize_openai_error(event.get('error', event))}, ensure_ascii=False)}\n\n"
                elif event_type in ("response.completed", "response.failed", "response.cancelled", "response.incomplete"):
                    break

            if not yielded_role:
                yield f"data: {json.dumps(create_chat_stream_chunk(request_id, model, role='assistant'), ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps(create_chat_stream_chunk(request_id, model, finish_reason='stop'), ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
    except httpx.TimeoutException:
        yield f"data: {json.dumps({'error': normalize_openai_error({'message': '上游请求超时', 'type': 'timeout_error', 'code': 'upstream_timeout'})}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
    except httpx.HTTPError as exc:
        yield f"data: {json.dumps({'error': normalize_openai_error({'message': str(exc), 'type': 'upstream_error'})}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"


async def collect_responses_stream_as_chat_completion(
    responses_request: dict[str, Any],
    upstream_url: str,
    headers: dict[str, str],
    model: str,
) -> JSONResponse:
    text_parts: list[str] = []
    final_response: dict[str, Any] = {}

    try:
        async with get_client().stream("POST", upstream_url, headers=headers, json=responses_request) as resp:
            if resp.status_code != 200:
                return create_error_response(await resp.aread(), resp.status_code)

            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data_str = line[6:].strip()
                if not data_str or data_str == "[DONE]":
                    continue
                try:
                    event = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                event_type = event.get("type")
                if event_type in ("response.output_text.delta", "response.refusal.delta"):
                    delta = event.get("delta", "")
                    if delta:
                        text_parts.append(str(delta))
                elif event_type == "response.error":
                    return create_error_response(event.get("error", event), 502)
                elif event_type == "response.completed":
                    response = event.get("response")
                    if isinstance(response, dict):
                        final_response = response
                elif event_type in ("response.failed", "response.cancelled", "response.incomplete"):
                    response = event.get("response")
                    if isinstance(response, dict) and response.get("error"):
                        return create_error_response(response["error"], 502)
                    break
    except httpx.TimeoutException:
        return create_error_response({"message": "上游请求超时", "type": "timeout_error", "code": "upstream_timeout"}, 504)
    except httpx.HTTPError as exc:
        return create_error_response({"message": str(exc), "type": "upstream_error"}, 502)

    if text_parts:
        final_response["output_text"] = "".join(text_parts)
    final_response.setdefault("status", "completed")
    final_response.setdefault("usage", {})
    return JSONResponse(create_chat_completion_response(final_response, model))


async def handle_chat_completions_via_responses(
    request: Request,
    original_body: bytes,
    config: dict[str, Any],
    api_key: str,
) -> Response | None:
    try:
        chat_request = json.loads(original_body)
    except json.JSONDecodeError:
        return None
    if not isinstance(chat_request, dict):
        return None
    if not should_bridge_chat_completions("chat/completions", chat_request, config):
        return None

    model = config["model"] if config["force_model"] or not chat_request.get("model") else chat_request["model"]
    responses_request = convert_chat_to_responses_request(chat_request, model)
    headers = apply_codex_responses_headers(
        build_upstream_headers(request, api_key, True),
        responses_request["client_metadata"],
    )
    upstream_url = build_upstream_url(config["upstream_base_url"], "responses", request.url.query)

    if chat_request.get("stream"):
        return StreamingResponse(
            stream_responses_as_chat_completions(responses_request, upstream_url, headers, model),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    return await collect_responses_stream_as_chat_completion(responses_request, upstream_url, headers, model)


@app.get("/admin", response_class=HTMLResponse)
async def admin_page():
    index_path = ADMIN_STATIC_DIR / "index.html"
    if index_path.is_file():
        return FileResponse(index_path)
    return HTMLResponse(ADMIN_HTML)


@app.post("/admin/api/login")
async def admin_login(req: LoginRequest):
    config = runtime_config.snapshot()
    if req.username != config["admin_username"] or not verify_password(req.password, runtime_config.admin_password):
        raise HTTPException(status_code=401, detail="用户名或密码不正确")
    return {"token": create_admin_token(req.username), "expires_in": ADMIN_TOKEN_TTL_SECONDS}


@app.get("/admin/api/config")
async def admin_get_config(request: Request):
    await require_admin(request)
    return build_admin_config()


@app.put("/admin/api/settings")
async def admin_update_settings(req: SettingsUpdateRequest, request: Request):
    await require_admin(request)
    try:
        runtime_config.update_settings(req.upstream_base_url, req.model, req.force_model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"message": "配置已更新", "config": build_admin_config()}


@app.put("/admin/api/keys")
async def admin_replace_keys(req: KeysUpdateRequest, request: Request):
    await require_admin(request)
    runtime_config.update_api_keys(normalize_key_list(req.keys))
    return {"message": "Key 列表已替换", "config": build_admin_config()}


@app.get("/admin/api/keys")
async def admin_get_keys(request: Request):
    await require_admin(request)
    return build_admin_config()["api_keys"]


@app.post("/admin/api/keys", status_code=201)
async def admin_add_key(req: KeyAddRequest, request: Request):
    await require_admin(request)
    key = req.key.strip()
    if not key:
        raise HTTPException(status_code=400, detail="Key 不能为空")
    keys = runtime_config.snapshot()["api_keys"]
    keys.append(key)
    runtime_config.update_api_keys(keys)
    return {"message": "Key 已添加", "config": build_admin_config()}


@app.delete("/admin/api/keys/{index}")
async def admin_delete_key(index: int, request: Request):
    await require_admin(request)
    keys = runtime_config.snapshot()["api_keys"]
    if index < 0 or index >= len(keys):
        raise HTTPException(status_code=400, detail="Key 序号超出范围")
    removed = keys.pop(index)
    runtime_config.update_api_keys(keys)
    return {"message": "Key 已删除", "removed_key": mask_key(removed), "config": build_admin_config()}


@app.get("/admin/api/proxy-keys")
async def admin_get_proxy_keys(request: Request):
    await require_admin(request)
    return build_admin_config()["proxy_api_keys"]


@app.put("/admin/api/proxy-keys")
async def admin_replace_proxy_keys(req: KeysUpdateRequest, request: Request):
    await require_admin(request)
    runtime_config.update_proxy_api_keys(normalize_key_list(req.keys))
    return {"message": "代理 Key 列表已替换", "config": build_admin_config()}


@app.post("/admin/api/proxy-keys", status_code=201)
async def admin_add_proxy_key(req: KeyAddRequest, request: Request):
    await require_admin(request)
    key = req.key.strip()
    if not key:
        raise HTTPException(status_code=400, detail="代理 Key 不能为空")
    keys = runtime_config.snapshot()["proxy_api_keys"]
    keys.append(key)
    runtime_config.update_proxy_api_keys(keys)
    return {"message": "代理 Key 已添加", "config": build_admin_config()}


@app.post("/admin/api/proxy-keys/generate", status_code=201)
async def admin_generate_proxy_key(request: Request):
    await require_admin(request)
    key = f"sk-proxy-{secrets.token_hex(24)}"
    keys = runtime_config.snapshot()["proxy_api_keys"]
    keys.append(key)
    runtime_config.update_proxy_api_keys(keys)
    return {"message": "代理 Key 已生成", "key": key, "config": build_admin_config()}


@app.delete("/admin/api/proxy-keys/{index}")
async def admin_delete_proxy_key(index: int, request: Request):
    await require_admin(request)
    keys = runtime_config.snapshot()["proxy_api_keys"]
    if index < 0 or index >= len(keys):
        raise HTTPException(status_code=400, detail="代理 Key 序号超出范围")
    removed = keys.pop(index)
    runtime_config.update_proxy_api_keys(keys)
    return {"message": "代理 Key 已删除", "removed_key": mask_key(removed), "config": build_admin_config()}


@app.put("/admin/api/password")
async def admin_update_password(req: PasswordUpdateRequest, request: Request):
    await require_admin(request)
    try:
        runtime_config.update_admin_password(req.old_password, req.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"message": "密码已更新"}


@app.post("/admin/api/reload")
async def admin_reload(request: Request):
    await require_admin(request)
    runtime_config.load()
    return {"message": "配置已从 .env 重载", "config": build_admin_config()}


@app.api_route("/v1/{upstream_path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy_v1(upstream_path: str, request: Request):
    config = runtime_config.snapshot()
    try:
        await validate_proxy_access(request)
        api_key = await resolve_upstream_api_key(request)
    except HTTPException as exc:
        return create_error_response(exc.detail, exc.status_code)
    original_body = await request.body()

    if upstream_path.strip("/") == "chat/completions":
        bridged_response = await handle_chat_completions_via_responses(request, original_body, config, api_key)
        if bridged_response is not None:
            return bridged_response

    body, body_is_json = maybe_rewrite_json_body(
        upstream_path,
        request.method,
        original_body,
        config["model"],
        config["force_model"],
    )

    upstream_url = build_upstream_url(config["upstream_base_url"], upstream_path, request.url.query)
    headers = build_upstream_headers(request, api_key, body_is_json)

    logger.info("%s /v1/%s -> %s", request.method, upstream_path, upstream_url)

    client = get_client()
    stream_context = client.stream(
        request.method,
        upstream_url,
        headers=headers,
        content=body if body else None,
    )

    try:
        upstream_response = await stream_context.__aenter__()
    except httpx.TimeoutException:
        return create_error_response(
            {"message": "上游请求超时", "type": "timeout_error", "code": "upstream_timeout"},
            504,
        )
    except httpx.HTTPError as exc:
        return create_error_response({"message": str(exc), "type": "upstream_error"}, 502)

    response_headers = filter_response_headers(upstream_response.headers)
    media_type = upstream_response.headers.get("content-type")

    return StreamingResponse(
        iter_upstream_response(upstream_response, stream_context),
        status_code=upstream_response.status_code,
        headers=response_headers,
        media_type=media_type,
    )


@app.options("/v1/{upstream_path:path}")
async def options_v1(upstream_path: str):
    return Response(status_code=204)


@app.get("/health")
async def health():
    config = runtime_config.snapshot()
    return {
        "status": "ok",
        "service": "codex-anyrouter-proxy",
        "upstream": config["upstream_base_url"],
        "default_model": config["model"],
        "force_model": config["force_model"],
        "configured_api_keys": len(config["api_keys"]),
        "proxy_api_key_enabled": bool(config["proxy_api_keys"]),
        "api_key_source": "admin/env" if config["api_keys"] else "request",
        "admin_url": "/admin",
    }


@app.get("/")
async def root():
    config = runtime_config.snapshot()
    return JSONResponse(
        {
            "service": "Codex AnyRouter Proxy",
            "mode": "openai-responses-passthrough",
            "upstream": config["upstream_base_url"],
            "admin_url": "/admin",
            "endpoints": [
                "POST /v1/responses",
                "GET /v1/models",
                "POST /v1/chat/completions",
                "GET|POST|PUT|PATCH|DELETE /v1/{path}",
            ],
        }
    )


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("CODEX_PROXY_PORT", "9996"))
    host = os.getenv("HOST", "0.0.0.0")
    config = runtime_config.snapshot()

    print(f"""
============================================================
              Codex AnyRouter Proxy
============================================================
  Proxy:    http://{host}:{port}
  Admin:    http://127.0.0.1:{port}/admin
  Upstream: {config["upstream_base_url"]}
  Model:    {config["model"]}
------------------------------------------------------------
  Codex config base_url: http://127.0.0.1:{port}/v1
============================================================
""")

    uvicorn.run(app, host=host, port=port)
