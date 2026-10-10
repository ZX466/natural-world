/**
 * client/src/net/anchorsApi.ts — 存档/读档 HTTP 客户端（批次 D4）。
 *
 * 后端契约（sim/api/anchors.py）：GET 列表 / POST 新建 / DELETE 删除 /
 * GET current 当前游标。**读档走 WS**（load_anchor 消息 → 分叉告知 +
 * 全量快照两帧），不在本模块。api_key 同族错误处理（戏外 meta shell）。
 */
import type { AnchorCreate, AnchorListItem } from './protocol';
import { readError } from './settingsApi';

const BASE = '/api/anchors';

export const anchorsApi = {
  async list(): Promise<AnchorListItem[]> {
    return json<AnchorListItem[]>(await fetch(BASE));
  },
  async create(data: AnchorCreate): Promise<AnchorListItem> {
    return json<AnchorListItem>(
      await fetch(BASE, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      }),
    );
  },
  async remove(id: string): Promise<void> {
    const res = await fetch(`${BASE}/${encodeURIComponent(id)}`, { method: 'DELETE' });
    if (!res.ok) throw await readError(res);
  },
  async current(): Promise<AnchorListItem> {
    return json<AnchorListItem>(await fetch(`${BASE}/current`));
  },
};

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw await readError(res);
  return (await res.json()) as T;
}
