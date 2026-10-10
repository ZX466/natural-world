/**
 * client/src/ui/SaveLoadPanel.tsx — 存档/读档面板（批次 D4）。
 *
 * 读档=分叉（DESIGN C6）：读档发起走 WS load_anchor（runtime 层），成功后
 * 服务端推分叉告知 + 全量快照两帧（前端零额外逻辑——镜像重置链路现成）。
 * 本面板只做戏外操作面：列表 / 新建 / 删除 / 读档按钮。
 * 版式：暗木墨色 shell，与戏内宣纸面板分层（见 ui.css）。
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

  const onLoad = useCallback((id: string) => {
    setBusy(true);
    try {
      runtime.loadAnchor(id);
      setNotice(null);
    } finally {
      setBusy(false);
    }
  }, []);

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
    <div className="od-menu od-menu--saveload">
      <div className="od-menu__head">
        <h2 className="od-menu__title">存档</h2>
        <button
          type="button"
          onClick={onSave}
          disabled={busy}
          className="od-menu__btn od-menu__btn--primary"
        >
          存一档
        </button>
      </div>
      {notice !== null && (
        <p className="od-menu__notice" role="alert" aria-live="polite">
          {notice}
        </p>
      )}
      {items.length === 0 ? (
        <p className="od-menu__empty">还没有存档。</p>
      ) : (
        <ul className="od-menu__list">
          {items.map((item) => (
            <li key={item.id} className="od-menu__row">
              <div className="od-menu__meta">
                <p className="od-menu__name" title={item.name}>
                  {item.name}
                </p>
                <p className="od-menu__label">{item.story_label}</p>
              </div>
              <div className="od-menu__acts">
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => onLoad(item.id)}
                  className="od-menu__btn"
                >
                  读档
                </button>
                <button
                  type="button"
                  disabled={busy || item.protected}
                  onClick={() => onDelete(item.id)}
                  className="od-menu__btn od-menu__btn--danger"
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
