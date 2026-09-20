/**
 * client/src/ui/SettingsPage.tsx — 设置页（戏外 meta shell，DESIGN §2 C3）。
 *
 * 本页只服务人类玩家：可用工程措辞，绝不进戏内叙事通道，也不回流 Agent prompt。
 * 契约：shared/protocol.ts（ProfileListItem 8 字段白名单；api_key 只提交、不回显）。
 */
import { useCallback, useEffect, useState, type ReactElement } from 'react';
import type { ProfileCreate, ProfileListItem } from '../net/protocol';
import {
  SettingsApiError,
  activateProfile,
  createProfile,
  deleteProfile,
  listProfiles,
  updateProfile,
} from '../net/settingsApi';

/** 编辑态：空字符串 = 新建；数字字段用字符串保存以适配受控 input。 */
interface FormState {
  id: string | null;
  name: string;
  base_url: string;
  model: string;
  api_key: string;
  temperature: string;
  max_tokens: string;
}

const EMPTY_FORM: FormState = {
  id: null,
  name: '',
  base_url: '',
  model: '',
  api_key: '',
  temperature: '0.7',
  max_tokens: '2048',
};

function formFrom(p: ProfileListItem): FormState {
  return {
    id: p.id,
    name: p.name,
    base_url: p.base_url,
    model: p.model,
    api_key: '', // 永不回显明文；留空 = 不修改
    temperature: String(p.temperature),
    max_tokens: String(p.max_tokens),
  };
}

function errorText(e: unknown): string {
  if (e instanceof SettingsApiError) {
    if (e.status === 422) return `输入不合法（422）：${e.message}`;
    if (e.status === 500) return `密钥服务不可用（500）：检查后端 LZ_MASTER_KEY 是否配置`;
    return `请求失败（${e.status}）：${e.message}`;
  }
  if (e instanceof TypeError) return '无法连接后端（sim 未启动？）';
  return e instanceof Error ? e.message : String(e);
}

export function SettingsPage({ onClose }: { onClose: () => void }): ReactElement {
  const [profiles, setProfiles] = useState<ProfileListItem[]>([]);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setProfiles(await listProfiles());
      setError(null);
    } catch (e) {
      setError(errorText(e));
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const set = <K extends keyof FormState>(k: K, v: FormState[K]): void => {
    setForm((f) => ({ ...f, [k]: v }));
  };

  async function submit(): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      const base = {
        name: form.name.trim(),
        base_url: form.base_url.trim(),
        model: form.model.trim(),
        temperature: Number(form.temperature),
        max_tokens: Number(form.max_tokens),
      };
      if (form.id === null) {
        const payload: ProfileCreate = { ...base, api_key: form.api_key };
        await createProfile(payload);
      } else {
        // api_key 留空 = 不修改（K1/K3）
        await updateProfile(
          form.id,
          form.api_key === '' ? base : { ...base, api_key: form.api_key },
        );
      }
      setForm(EMPTY_FORM); // 提交后清空 state（含 api_key）
      await refresh();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  async function onActivate(id: string): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      await activateProfile(id);
      await refresh();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  async function onDelete(p: ProfileListItem): Promise<void> {
    if (!window.confirm(`删除配置「${p.name}」？此操作不可撤销。`)) return;
    setBusy(true);
    setError(null);
    try {
      await deleteProfile(p.id);
      if (form.id === p.id) setForm(EMPTY_FORM);
      await refresh();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  const inputCls =
    'w-full rounded border border-stone-600 bg-stone-800 px-2 py-1 text-sm text-stone-100';

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-stone-950/98 p-6 text-stone-200">
      <header className="mb-4 flex items-center justify-between border-b border-stone-700 pb-2">
        <h1 className="text-lg font-semibold">模型设置</h1>
        <button
          type="button"
          onClick={onClose}
          className="rounded bg-stone-700 px-3 py-1 text-sm hover:bg-stone-600"
        >
          返回
        </button>
      </header>

      {error !== null && (
        <div className="mb-3 rounded border border-rose-700 bg-rose-950 px-3 py-2 text-sm text-rose-200">
          {error}
        </div>
      )}

      <div className="grid min-h-0 flex-1 grid-cols-[1fr_20rem] gap-6">
        {/* 列表 */}
        <section className="min-h-0 overflow-auto">
          <h2 className="mb-2 text-sm text-stone-400">已配置档案</h2>
          {profiles.length === 0 ? (
            <p className="text-sm text-stone-500">（暂无配置）</p>
          ) : (
            <ul className="space-y-2">
              {profiles.map((p) => (
                <li
                  key={p.id}
                  className={`rounded border px-3 py-2 ${
                    p.active
                      ? 'border-emerald-600 bg-emerald-950/40'
                      : 'border-stone-700 bg-stone-900'
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{p.name}</span>
                    {p.active && <span className="text-xs text-emerald-400">使用中</span>}
                    <span className="ml-auto flex gap-1">
                      <button
                        type="button"
                        disabled={busy || p.active}
                        onClick={() => void onActivate(p.id)}
                        className="rounded bg-stone-700 px-2 py-0.5 text-xs hover:bg-stone-600 disabled:opacity-40"
                      >
                        激活
                      </button>
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => setForm(formFrom(p))}
                        className="rounded bg-stone-700 px-2 py-0.5 text-xs hover:bg-stone-600 disabled:opacity-40"
                      >
                        编辑
                      </button>
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => void onDelete(p)}
                        className="rounded bg-rose-900 px-2 py-0.5 text-xs hover:bg-rose-800 disabled:opacity-40"
                      >
                        删除
                      </button>
                    </span>
                  </div>
                  <dl className="mt-1 grid grid-cols-2 gap-x-4 text-xs text-stone-400">
                    <div>
                      <dt className="inline">Base URL：</dt>
                      <dd className="inline text-stone-300">{p.base_url}</dd>
                    </div>
                    <div>
                      <dt className="inline">模型：</dt>
                      <dd className="inline text-stone-300">{p.model}</dd>
                    </div>
                    <div>
                      <dt className="inline">温度：</dt>
                      <dd className="inline text-stone-300">{p.temperature}</dd>
                    </div>
                    <div>
                      <dt className="inline">Max tokens：</dt>
                      <dd className="inline text-stone-300">{p.max_tokens}</dd>
                    </div>
                    <div>
                      <dt className="inline">密钥：</dt>
                      <dd className="inline text-stone-300">{p.api_key_hint}</dd>
                    </div>
                  </dl>
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* 表单 */}
        <section className="rounded border border-stone-700 bg-stone-900 p-3">
          <h2 className="mb-3 text-sm text-stone-400">
            {form.id === null ? '新建档案' : '编辑档案'}
          </h2>
          <div className="space-y-2">
            <label className="block text-xs">
              名称
              <input
                className={inputCls}
                value={form.name}
                maxLength={64}
                onChange={(e) => set('name', e.target.value)}
              />
            </label>
            <label className="block text-xs">
              Base URL
              <input
                className={inputCls}
                value={form.base_url}
                onChange={(e) => set('base_url', e.target.value)}
              />
            </label>
            <label className="block text-xs">
              模型
              <input
                className={inputCls}
                value={form.model}
                onChange={(e) => set('model', e.target.value)}
              />
            </label>
            <label className="block text-xs">
              API Key{form.id !== null && <span className="text-stone-500">（留空则不修改）</span>}
              <input
                className={inputCls}
                type="password"
                autoComplete="off"
                value={form.api_key}
                onChange={(e) => set('api_key', e.target.value)}
              />
            </label>
            <div className="flex gap-2">
              <label className="block flex-1 text-xs">
                温度
                <input
                  className={inputCls}
                  type="number"
                  min={0}
                  max={2}
                  step={0.1}
                  value={form.temperature}
                  onChange={(e) => set('temperature', e.target.value)}
                />
              </label>
              <label className="block flex-1 text-xs">
                Max tokens
                <input
                  className={inputCls}
                  type="number"
                  min={1}
                  max={32768}
                  value={form.max_tokens}
                  onChange={(e) => set('max_tokens', e.target.value)}
                />
              </label>
            </div>
          </div>
          <div className="mt-4 flex gap-2">
            <button
              type="button"
              disabled={busy}
              onClick={() => void submit()}
              className="rounded bg-emerald-700 px-3 py-1 text-sm hover:bg-emerald-600 disabled:opacity-40"
            >
              {form.id === null ? '新建' : '保存'}
            </button>
            {form.id !== null && (
              <button
                type="button"
                disabled={busy}
                onClick={() => setForm(EMPTY_FORM)}
                className="rounded bg-stone-700 px-3 py-1 text-sm hover:bg-stone-600 disabled:opacity-40"
              >
                取消
              </button>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
