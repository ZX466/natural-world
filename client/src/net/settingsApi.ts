/**
 * client/src/net/settingsApi.ts — 设置页 HTTP 客户端（戏外 meta shell）。
 *
 * 契约来自 shared/protocol.ts（openapi-typescript 生成物，真相源 sim/api/settings.py）。
 * 本页属戏外 meta shell（DESIGN §2 C3）：可用工程措辞；api_key 永不回显（K5）。
 * 走同源 /api（vite dev 代理 → sim:8000），避免 CORS。
 */
import type { ProfileCreate, ProfileListItem, ProfileUpdate } from './protocol';

const BASE = '/api/settings/profiles';

/** 结构化错误：携带 HTTP 状态码与后端 detail（戏外可工程措辞）。 */
export class SettingsApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = 'SettingsApiError';
  }
}

export async function readError(res: Response): Promise<SettingsApiError> {
  let detail = `请求失败（HTTP ${res.status}）`;
  try {
    const body: unknown = await res.json();
    if (body !== null && typeof body === 'object' && 'detail' in body) {
      const d = (body as { detail: unknown }).detail;
      detail = typeof d === 'string' ? d : JSON.stringify(d);
    }
  } catch {
    // 非 JSON 响应：保留默认文案
  }
  return new SettingsApiError(res.status, detail);
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw await readError(res);
  return (await res.json()) as T;
}

export async function listProfiles(): Promise<ProfileListItem[]> {
  return json<ProfileListItem[]>(await fetch(BASE));
}

export async function createProfile(data: ProfileCreate): Promise<ProfileListItem> {
  return json<ProfileListItem>(
    await fetch(BASE, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }),
  );
}

export async function updateProfile(id: string, data: ProfileUpdate): Promise<ProfileListItem> {
  return json<ProfileListItem>(
    await fetch(`${BASE}/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }),
  );
}

export async function deleteProfile(id: string): Promise<void> {
  const res = await fetch(`${BASE}/${encodeURIComponent(id)}`, { method: 'DELETE' });
  if (!res.ok) throw await readError(res);
}

export async function activateProfile(id: string): Promise<ProfileListItem> {
  return json<ProfileListItem>(
    await fetch(`${BASE}/${encodeURIComponent(id)}/activate`, { method: 'POST' }),
  );
}

// ── D13：拉取模型 / 测试连接（戏外调试面）──────────────────────────

export interface ListModelsResult {
  ok: boolean;
  models: string[];
  reason: string | null;
}

/** 拉对方 /models 清单（OpenAI 兼容）。失败也返回结构化结果（不抛）。 */
export async function listRemoteModels(baseUrl: string, apiKey: string): Promise<ListModelsResult> {
  const res = await fetch(`${BASE}/models`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ base_url: baseUrl, api_key: apiKey }),
  });
  return json<ListModelsResult>(res);
}

export interface TestConnectionResult {
  ok: boolean;
  latency_ms: number | null;
  reason: string | null;
}

/** 极小对话请求（max_tokens=1）测连通性。失败也返回结构化结果（不抛）。 */
export async function testConnection(
  baseUrl: string,
  model: string,
  apiKey: string,
): Promise<TestConnectionResult> {
  const res = await fetch(`${BASE}/test`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ base_url: baseUrl, model, api_key: apiKey }),
  });
  return json<TestConnectionResult>(res);
}
