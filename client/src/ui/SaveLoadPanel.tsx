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
import { useUiStore } from '../store/uiStore';
import { nextSaveName } from './save-names';
import { storyLabel } from './labels';

export function SaveLoadPanel(): ReactElement {
  const [items, setItems] = useState<AnchorListItem[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  /** 读档失败（error 帧 ref=load_anchor → store）：异步到达，不在 onLoad 的
   *  同步 try/finally 里，因此单列一个展示位。 */
  const loadError = useUiStore((s) => s.loadError);
  /** 读档在途（D3）：**由帧驱动**（`runtime.loadAnchor` 置位，`full_snapshot` /
   *  error 清除）。不能用本地 busy——`onLoad` 是同步的，`finally` 立刻清回，
   *  大库读档 20s+ 里按钮从未真禁用（可连点双 fork）。 */
  const loadPending = useUiStore((s) => s.loadPending);
  /** 分叉告知（D4，session_state.notice）。服务端过闸的戏内口语行，
   *  修前被 ws.ts 直接丢弃 ⇒ 读档后玩家不知道世界换线了。 */
  const forkNotice = useUiStore((s) => s.forkNotice);
  /** 面板提示：本面板同步失败（notice）优先，其次读档失败（loadError）。
   *  空串是服务端终扫 fail-closed 的结果（不给玩家看未过闸文本）⇒ 不渲染空提示框。 */
  const noticeText = notice ?? loadError;
  const message = noticeText !== null && noticeText !== '' ? noticeText : null;

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
      // D6-②：按现存默认名里的最大编号 +1，不能用 items.length + 1
      //（删档后编号回退 ⇒ 与现存档重名，列表里分不出哪个是新的）。
      await anchorsApi.create({ name: nextSaveName(items) });
      await refresh();
      setNotice(null);
    } catch (err) {
      setNotice(err instanceof Error ? err.message : '存档失败');
    } finally {
      setBusy(false);
    }
  }, [items, refresh]);

  const onLoad = useCallback((id: string) => {
    // 只做「发请求 + 清本面板的同步失败文案」。在途态归 store（帧驱动）：
    // 这里若 setBusy(true) 再 finally 清回，等于没禁用（见 loadPending 注释）。
    setNotice(null);
    runtime.loadAnchor(id);
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
          disabled={busy || loadPending}
          className="od-menu__btn od-menu__btn--primary"
        >
          存一档
        </button>
      </div>
      {loadPending && (
        // D3：读档等待态。措辞与快进过渡同口径（ws.py:1227 docstring 早已承诺
        // 「前端在等待期显示『片刻后……』叙事化过渡」，此前代码里根本没有）。
        <p className="od-menu__pending" role="status" aria-live="polite">
          片刻后……
        </p>
      )}
      {forkNotice !== null && forkNotice !== '' && (
        // 分叉告知优先于失败文案：它是「世界已换线」的确认，不是错误。
        <p className="od-menu__notice od-menu__notice--fork" role="status">
          {forkNotice}
        </p>
      )}
      {message !== null && (
        <p className="od-menu__notice" role="alert" aria-live="polite">
          {message}
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
                <p className="od-menu__label">{storyLabel(item.story_label)}</p>
              </div>
              <div className="od-menu__acts">
                <button
                  type="button"
                  disabled={busy || loadPending}
                  onClick={() => onLoad(item.id)}
                  className="od-menu__btn"
                >
                  读档
                </button>
                <button
                  type="button"
                  disabled={busy || loadPending || item.protected}
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
