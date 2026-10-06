/**
 * client/src/ui/SaveLoadPanel.tsx — 存档/读档面板（批次 D4）。
 *
 * 读档=分叉（DESIGN C6）：读档发起走 WS load_anchor（runtime 层），成功后
 * 服务端推分叉告知 + 全量快照两帧（前端零额外逻辑——镜像重置链路现成）。
 * 本面板只做戏外操作面：列表 / 新建 / 删除 / 读档按钮。
 */
import { useCallback, useEffect, useState, type ReactElement } from 'react';
import { anchorsApi } from '../net/anchorsApi';
import type { AnchorListItem } from '../net/protocol';
import { runtime } from '../game/runtime';

export function SaveLoadPanel(): ReactElement {
  const [items, setItems] = useState<AnchorListItem[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setItems(await anchorsApi.list());
    } catch (err) {
      setNotice(err instanceof Error ? err.message : '读取存档失败');
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const onSave = useCallback(async () => {
    setBusy(true);
    try {
      const idx = items.length + 1;
      await anchorsApi.create({ name: `游历 ${idx}` });
      await refresh();
      setNotice(null);
    } catch (err) {
      setNotice(err instanceof Error ? err.message : '存档失败');
    } finally {
      setBusy(false);
    }
  }, [items.length, refresh]);

  const onLoad = useCallback(
    (id: string) => {
      setBusy(true);
      try {
        runtime.loadAnchor(id);
        setNotice(null);
      } finally {
        setBusy(false);
      }
    },
    [],
  );

  const onDelete = useCallback(
    async (id: string) => {
      setBusy(true);
      try {
        await anchorsApi.remove(id);
        await refresh();
      } catch (err) {
        setNotice(err instanceof Error ? err.message : '删除失败');
      } finally {
        setBusy(false);
      }
    },
    [refresh],
  );

  return (
    <div className="border-b border-stone-700 bg-stone-900/95 p-3">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-xs font-semibold tracking-widest text-stone-400">存档</h2>
        <button
          type="button"
          onClick={onSave}
          disabled={busy}
          className="rounded bg-amber-500 px-3 py-1 text-xs font-medium text-stone-900 hover:bg-amber-400 disabled:opacity-50"
        >
          存一档
        </button>
      </div>
      {notice !== null && (
        <p className="mb-2 text-xs text-rose-300" role="alert">
          {notice}
        </p>
      )}
      {items.length === 0 ? (
        <p className="text-xs text-stone-500">还没有存档。</p>
      ) : (
        <ul className="space-y-1.5">
          {items.map((item) => (
            <li
              key={item.id}
              className="flex items-center justify-between rounded bg-stone-800/70 px-2.5 py-1.5"
            >
              <div className="min-w-0">
                <p className="truncate text-xs text-stone-200">{item.name}</p>
                <p className="text-[10px] text-stone-400">{item.story_label}</p>
              </div>
              <div className="ml-2 flex shrink-0 gap-1">
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => onLoad(item.id)}
                  className="rounded bg-stone-700 px-2 py-0.5 text-[10px] text-stone-200 hover:bg-stone-600 disabled:opacity-50"
                >
                  读档
                </button>
                <button
                  type="button"
                  disabled={busy || item.protected}
                  onClick={() => onDelete(item.id)}
                  className="rounded bg-stone-700 px-2 py-0.5 text-[10px] text-stone-400 hover:bg-rose-700 hover:text-stone-100 disabled:opacity-30"
                >
                  删
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
