export type AdminConfig = {
  settings: {
    upstream_base_url: string;
    model: string;
    force_model: boolean;
  };
  api_keys: {
    count: number;
    masked: string[];
  };
  proxy_api_keys: {
    count: number;
    values: string[];
    masked: string[];
    enabled: boolean;
  };
  admin: {
    username: string;
    using_default_password: boolean;
  };
  service: {
    port: number;
    env_file: string;
  };
};

export type Health = {
  status: string;
  service: string;
  upstream: string;
  default_model: string;
  force_model: boolean;
  configured_api_keys: number;
  proxy_api_key_enabled: boolean;
  api_key_source: string;
  admin_url: string;
};

const TOKEN_KEY = 'codex-anyrouter-admin-token';

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || '';
}

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...((init.headers as Record<string, string>) || {}),
  };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(path, { ...init, headers });
  const data = await response.json().catch(() => ({}));

  if (response.status === 401) {
    if (path === '/admin/api/login') {
      throw new Error(data.detail || '用户名或密码不正确');
    }
    clearToken();
    throw new Error('登录已过期，请重新登录');
  }

  if (!response.ok) {
    throw new Error(data.detail || data.error?.message || `HTTP ${response.status}`);
  }

  return data as T;
}

export async function login(username: string, password: string) {
  const data = await request<{ token: string; expires_in: number }>('/admin/api/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  });
  setToken(data.token);
  return data;
}

export async function getConfig() {
  return request<AdminConfig>('/admin/api/config');
}

export async function getHealth() {
  return request<Health>('/health', { headers: {} });
}

export async function updateSettings(payload: AdminConfig['settings']) {
  return request<{ message: string; config: AdminConfig }>('/admin/api/settings', {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export async function reloadConfig() {
  return request<{ message: string; config: AdminConfig }>('/admin/api/reload', { method: 'POST' });
}

export async function addUpstreamKey(key: string) {
  return request<{ message: string; config: AdminConfig }>('/admin/api/keys', {
    method: 'POST',
    body: JSON.stringify({ key }),
  });
}

export async function replaceUpstreamKeys(keys: string[]) {
  return request<{ message: string; config: AdminConfig }>('/admin/api/keys', {
    method: 'PUT',
    body: JSON.stringify({ keys }),
  });
}

export async function deleteUpstreamKey(index: number) {
  return request<{ message: string; config: AdminConfig }>(`/admin/api/keys/${index}`, {
    method: 'DELETE',
  });
}

export async function addProxyKey(key: string) {
  return request<{ message: string; config: AdminConfig }>('/admin/api/proxy-keys', {
    method: 'POST',
    body: JSON.stringify({ key }),
  });
}

export async function generateProxyKey() {
  return request<{ message: string; key: string; config: AdminConfig }>('/admin/api/proxy-keys/generate', {
    method: 'POST',
  });
}

export async function deleteProxyKey(index: number) {
  return request<{ message: string; config: AdminConfig }>(`/admin/api/proxy-keys/${index}`, {
    method: 'DELETE',
  });
}

export async function changePassword(oldPassword: string, newPassword: string) {
  return request<{ message: string }>('/admin/api/password', {
    method: 'PUT',
    body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }),
  });
}
