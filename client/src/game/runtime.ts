/**
 * client/src/game/runtime.ts — 前端运行时单例：镜像 + WS 驱动。
 *
 * mock 分支已删（2026-10-12，README §3 待办清欠）：sim 未起时前端保持诚实——
 * 状态停在 connecting/reconnecting/closed，无假数据、无假时钟；
 * 所有 send 在断线时由 ws.ts 静默丢弃（不炸），恢复连接后镜像经快照重建。
 */
import { WorldMirror } from './world-mirror';
import { WsClient, setControlStateSink, type WsStatus } from '../net/ws';
import { fetchWorldMap, assembleCollision, assembleGround } from '../net/worldApi';
import { worldClock } from './clock';
import { useUiStore, type Speed } from '../store/uiStore';
import { rendererFromSearch } from './render/presentation';
import type { MoveRequestMessage, VoxelRequestMessage } from '../net/protocol';
import { movementFailure } from './movement';
import { validElevation } from './locomotion';
import { worldAudio } from './audio';

export const worldMirror = new WorldMirror();

const SIM_WS_URL = 'ws://127.0.0.1:8000/ws';
/** player_impulse.text 上限（PlayerImpulseMessage schema maxLength 64 同源） */
export const IMPULSE_MAX_LEN = 64;
const IMPULSE_TOO_LONG_MSG = '话说得太长了，说不清。';
/** D14 头顶气泡停留时长（ms；阅读 15 字约 4s，取整档） */
const BUBBLE_DURATION_MS = 4000;

class Runtime {
  private ws: WsClient | null = null;
  private mapRevision = 0;

  start(): void {
    this.ws = new WsClient(SIM_WS_URL, worldMirror, {
      onStatus: (status: WsStatus) => {
        worldAudio.status(status);
        useUiStore.getState().setWsStatus(status);
        if (status !== 'open') {
          worldMirror.voxelDig = null;
          useUiStore.getState().setVoxelInventory(null);
          this.mapRevision += 1;
          // D3：掉线时服务端既不会回 error 帧、也不会推 full_snapshot，
          // 读档在途标记只能在这里收尾，否则「片刻后……」挂到重连为止。
          useUiStore.getState().setLoadPending(false);
        }
        // H-1：真实链路起 clock（世界静止无 delta 时前端时钟仍平滑推进，R3）。
        if (status === 'open') {
          worldClock.start();
        }
      },
      onSnapshot: () => {
        worldAudio.snapshot(worldMirror);
        useUiStore.getState().setWsStatus('open');
        // 世界已恢复 ⇒ 上一次读档失败文案必须撤掉，否则成功读档后面板仍挂着
        // 「这个档读不出来了。」（2026-11-03 code review 指出的时序缺口）。
        useUiStore.getState().setLoadError(null);
        // D3：读档在途标记同样在此清除——`full_snapshot` 是「世界已恢复」的唯一
        // 权威信号（分叉告知/时钟帧都可能在它之前到）。重连也会走这里，无副作用。
        useUiStore.getState().setLoadPending(false);
        // HTTP is authoritative for unedited cells after a branch switch too.
        void this.loadWorldMap();
      },
      onVoxelState: (msg) => useUiStore.getState().setVoxelInventory({ ...msg.inventory }),
      onDelta: (msg) => {
        // 批次 A：计划看板（delta 即全量替换语义，sim 侧 PlanDelta[] 无增删协议）
        if (msg.plan) useUiStore.getState().setPlans([...msg.plan]);
        if (msg.structures?.length) void this.loadWorldMap();
        worldAudio.delta(msg, worldMirror);
      },
      onCombatEvent: (msg) => worldAudio.combat(msg, worldMirror),
      onMonologue: (msg) => {
        // 批次 D10 分流：bubble = 村民的公开嘟囔 → 街谈巷议 + 头顶气泡（D14）；
        // thought/plan = 陈默的心声 → 心之声面板。
        // monologue 帧无 actor 字段（W7 字段最小化），语义路由按 form 定。
        // D12：bubble 帧可选 name（说话人戏内名）随行进署名。
        if (msg.form === 'bubble') {
          useUiStore.getState().pushChatter(msg.name ?? null, msg.content);
          // D14：头顶气泡（有署名才冒——无名嘟囔无处定位）
          if (msg.name) {
            worldMirror.setBubble(msg.name, msg.content, BUBBLE_DURATION_MS, Date.now());
          }
        } else {
          useUiStore.getState().pushMonologue(msg.form, msg.content);
        }
      },
      onMonologueHistory: (history) => {
        // 重连/读档快照的心声历史：**整组替换**，不逐条追加。
        // 快照带的是最近 N 条的完整投影；按增量喂会每重连一次整屏重复
        //（2026-11-05 实机截图：两条一模一样的气味独白）。
        // 两面板分流口径与 onMonologue 一致：bubble → 街谈巷议，其余 → 心之声。
        // 气泡不重放（历史是面板文本，不是此刻正在冒的头顶气泡）。
        const store = useUiStore.getState();
        const chatter = history.filter((f) => f.form === 'bubble');
        const monologues = history.filter((f) => f.form !== 'bubble');
        store.replaceChatter(chatter.map((f) => ({ name: f.name ?? null, content: f.content })));
        store.replaceMonologues(monologues.map((f) => ({ form: f.form, content: f.content })));
      },
      onImpulseFeedback: (msg) => {
        const store = useUiStore.getState();
        store.setLastImpulseCue(msg.cue);
        store.setImpulseError(null);
        store.pushMonologue(msg.reaction_monologue.form, msg.reaction_monologue.content);
        // Iso also presents the existing reaction above its actor; the world and
        // protocol remain authoritative, and the explicit flat presentation is retained.
        const name = worldMirror.actors.get(worldMirror.protagonist ?? '')?.name;
        if (name && rendererFromSearch(globalThis.location?.search ?? '') === 'iso') {
          worldMirror.setBubble(
            name,
            msg.reaction_monologue.content,
            BUBBLE_DURATION_MS,
            Date.now(),
          );
        }
      },
      onError: (msg) => {
        if (msg.ref === 'move_request') {
          useUiStore.getState().setVoxelError('那处走不过去。');
        }
        if (msg.ref === 'jump_request') {
          useUiStore.getState().setVoxelError('那处跳不过去。');
          worldMirror.locomotionRevision += 1;
        }
        if (msg.ref === 'voxel_request') {
          useUiStore
            .getState()
            .setVoxelError(msg.code === 'bad_target' ? msg.message : '这会儿动不了土。');
        }
        // 读档失败（load_failed）必须有玩家可见位：服务端已备好过闸文案，
        // 修前此处静默丢弃 ⇒ 点「读档」面板毫无反应（2026-11-03 实机发现）。
        // **只认两种玩家可见 code**：`load_failed`（文案已过终扫）与 `bad_anchor`
        //（「没这个档。」）。`bad_channel`/`unknown_type` 等是工程措辞
        //（"channel mismatch"），漏进面板就破了 §4.5 戏内文风 ⇒ 走戏内兜底。
        if (msg.ref === 'load_anchor') {
          const visible = msg.code === 'load_failed' || msg.code === 'bad_anchor';
          const store = useUiStore.getState();
          store.setLoadError(visible ? msg.message : '这个档读不出来了。');
          // D3：失败是读档在途的**另一个终态**——不清则按钮永久禁用。
          store.setLoadPending(false);
        }
        if (msg.ref === 'player_impulse') {
          // 同一白名单口径（§4.5）：`bad_impulse`/`impulse_too_long` 的文案是戏内口语，
          // 可直显。**`bad_channel` 会以 ref=player_impulse 到达**（服务端分发块用消息
          // type 当 ref，ws.py:995 回 "channel mismatch"）⇒ 必须挡，否则英文进念头栏。
          const visible = msg.code === 'bad_impulse' || msg.code === 'impulse_too_long';
          useUiStore.getState().setImpulseError(visible ? msg.message : '这个念头进不去。');
        }
        // D5：`set_control` 被拒（bad_speed/bad_action/bad_advance）此前无任何落点。
        // 服务端 6 条文案都是戏内口语（ws.py:1110-1145），可直接显示；
        // `bad_channel` 等工程措辞走兜底（同 load_anchor 的白名单口径，§4.5）。
        if (msg.ref === 'set_control') {
          // 三种 code 的文案都是戏内口语：bad_speed「快不了那么慢，也快不了那么快。」
          // bad_action「本来就没停。」/「不知道要怎么调。」
          // bad_advance「一下子走不了那么远。」/「停着呢，走不了。」/「日子已经在往前走了。」
          const visible =
            msg.code === 'bad_speed' || msg.code === 'bad_action' || msg.code === 'bad_advance';
          useUiStore.getState().setControlError(visible ? msg.message : '这会儿调不了。');
        }
      },
      onSessionState: (msg) => {
        // 主树 D4：这两个键此前在 ws.ts 里被直接丢弃。
        // `notice` 是服务端过闸后的戏内口语行（ws.py::fork_notice 对存量档名做终扫，
        // 命中禁词退化为无档名兜底行），可直接显示。
        // `anchor` 只含 name + story_label（零 tick/seq/branch_id，§4.6）。
        // null 是合法形状（连接首帧、非读档场景）⇒ 置空而非保留旧值。
        const store = useUiStore.getState();
        store.setForkNotice(msg.notice ?? null);
        store.setSessionAnchor(msg.anchor ?? null);
      },
      onControlAck: (msg) => {
        // 批次 D11：控制回执权威面——pause/resume/set_speed 后服务端真值回写
        // store（TopBar 暂停按钮文案 + 倍速高亮跟随）。applied=false 当前协议
        // 恒 true（8.1 占位）；错误路径走 error 帧不经此处。
        const store = useUiStore.getState();
        if (msg.paused !== undefined && msg.paused !== null) {
          store.setPaused(msg.paused);
        }
        if (msg.speed !== undefined && msg.speed !== null) {
          store.setSpeed(msg.speed as Speed);
        }
        // fast_forward 的 ack 不带 speed/paused：受理即终态（世界已推进完），
        // 无本地状态可回写（全量快照随后由 dispatch 的 snapshot 分支消费）。
      },
    });
    this.ws.connect();
    this.loadWorldMap();
  }

  /** 静态层走 HTTP（codex 意见 5）：缺它 handlePointer 的 map=null 守卫
   *  吞掉一切点击（M7 修复的第二个断链）。M7-T6 增地面层（瓦片渲染）。
   *  后端未起时镜像保持 null（诚实态），点击守卫维持。 */
  private async loadWorldMap(): Promise<void> {
    const revision = ++this.mapRevision;
    try {
      const raw = await fetchWorldMap();
      if (revision !== this.mapRevision) return;
      worldMirror.setMap({
        w: raw.w,
        h: raw.h,
        tileset: raw.tileset,
        collision: assembleCollision(raw.w, raw.h, raw.chunks),
        ground: assembleGround(raw.w, raw.h, raw.chunks),
        // 静态结构锚点随图下发：占地面已在 collision 里不可走，客户端只负责
        // 把模型立在同一个矩形上，绝不自己扫地形猜位置（那会前后端分叉）。
        structures: raw.structures ?? {},
      });
    } catch {
      // 后端未起或网络失败：镜像保持 null；WS 指数退避重连由 ws.ts 负责
    }
  }

  /** V4a 手势只发送编辑意图；库存和完成时刻始终由 sim 决定。 */
  requestVoxel(
    action: VoxelRequestMessage['action'],
    x: number,
    y: number,
    material?: VoxelRequestMessage['material'],
  ): void {
    const state = useUiStore.getState();
    state.setVoxelError(null);
    if (state.wsStatus !== 'open') {
      state.setVoxelError('这会儿动不了土。');
      return;
    }
    this.ws?.send({
      type: 'voxel_request',
      channel: 'render',
      action,
      x,
      y,
      ...(action === 'place' ? { material: material ?? state.voxelMaterial ?? 'earth' } : {}),
    });
  }

  /** 玩家控制（TopBar 倍速按钮）——真实链路发 set_control。 */
  sendControl(action: 'pause' | 'resume' | 'set_speed', speed?: Speed): void {
    // D5：新请求清旧拒收文案——否则顶栏那一行会永久挂着（无自动消失逻辑）。
    useUiStore.getState().setControlError(null);
    if (action === 'set_speed' && speed !== undefined) {
      this.ws?.send({ type: 'set_control', channel: 'control', action, speed });
      return;
    }
    if (action === 'pause' || action === 'resume') {
      this.ws?.send({ type: 'set_control', channel: 'control', action });
    }
  }

  /** WorldScene 点击寻路请求：专用 move_request 消息（TASK-K01；W5 红线——
   *  移动绝不走 impulse 文本旁路，codex C04 抽查记账项）。 */
  requestMove(x: number, y: number, gait?: 'walk' | 'run'): boolean {
    const state = useUiStore.getState();
    if (
      state.wsStatus !== 'open' ||
      this.ws === null ||
      (gait !== undefined && !this.ws.worldReady)
    ) {
      state.setVoxelError('这会儿走不了。');
      return false;
    }
    const map = worldMirror.map;
    const actor = worldMirror.actors.get(worldMirror.protagonist ?? '');
    if (!map || !actor) {
      state.setVoxelError('这会儿走不了。');
      return false;
    }
    if (actor.jump?.active) return false;
    const failure =
      gait === undefined
        ? movementFailure(map, actor, { x, y })
        : movementFailure(
            map,
            actor,
            { x, y },
            (px, py) => worldMirror.heightAt(px, py),
            actor.elevation ?? worldMirror.heightAt(actor.x, actor.y),
          );
    if (failure !== null) {
      state.setVoxelError(failure);
      return false;
    }
    state.setVoxelError(null);
    const move: Omit<MoveRequestMessage, 'v' | 'ws_seq'> = {
      type: 'move_request',
      channel: 'render',
      target_x: x,
      target_y: y,
      ...(gait === undefined ? {} : { gait }),
    };
    this.ws.send(move);
    return true;
  }

  /** Only send intent after this connection's authoritative world is ready. */
  requestJump(x: number, y: number, gait: 'walk' | 'run' = 'walk'): boolean {
    const state = useUiStore.getState();
    const map = worldMirror.map;
    const actor = worldMirror.actors.get(worldMirror.protagonist ?? '');
    if (state.wsStatus !== 'open' || !this.ws?.worldReady || !map || !actor || actor.jump?.active) {
      return false;
    }
    if (
      !Number.isInteger(x) ||
      !Number.isInteger(y) ||
      x < 0 ||
      y < 0 ||
      x >= map.w ||
      y >= map.h
    ) {
      state.setVoxelError('那处跳不过去。');
      return false;
    }
    const startHeight = actor.elevation ?? worldMirror.heightAt(actor.x, actor.y);
    const height = worldMirror.heightAt(x, y);
    const reach = gait === 'run' ? 2 : 1;
    if (
      !validElevation(startHeight) ||
      !validElevation(height) ||
      Math.max(Math.abs(x - actor.x), Math.abs(y - actor.y)) > reach ||
      height === 0 ||
      Math.abs(height - startHeight) > 2
    ) {
      state.setVoxelError('那处跳不过去。');
      return false;
    }
    state.setVoxelError(null);
    this.ws.send({ type: 'jump_request', channel: 'render', target_x: x, target_y: y, gait });
    return true;
  }

  /** 读档=分叉（批次 D4）：发 load_anchor，成功后服务端推「分叉告知 + 全量
   *  快照」两帧——镜像重置与游标指针消费链路现成（ws.ts dispatch/session_state）。 */
  loadAnchor(anchorId: string): void {
    // 新请求先清旧失败文案：否则上一次失败会一直挂在存档面板上
    const store = useUiStore.getState();
    store.setLoadError(null);
    // 断线时 ws.ts 静默丢弃 send ⇒ 没有 full_snapshot、也没有 error 帧，
    // 在途标记会永久挂着（面板永远「片刻后……」、按钮永远禁用）。这里先拒。
    if (store.wsStatus !== 'open' || this.ws === null) {
      store.setLoadError('这会儿连不上，读不了档。');
      return;
    }
    // 在途中再点一次：`disabled` 是 React 渲染后才生效的属性，双击的两次
    // onClick 可以在同一帧内跑完 ⇒ 只有请求侧判重能拦住第二个 fork。
    if (store.loadPending) return;
    // 上一次分叉告知属于旧请求：不清则新一次读档的「片刻后……」旁边还挂着
    // 「你回到了「X」那段日子」（D4）。
    store.setForkNotice(null);
    // D3：在途标记**由帧**清除（full_snapshot / error{ref:load_anchor}），
    // 不能用同步 try/finally——大库读档重放 20s+，本地 busy 会立刻清回，
    // 按钮等于从未禁用（可连点两次 ⇒ 服务端队列无判重 ⇒ 连续分叉两次）。
    store.setLoadPending(true);
    this.ws?.send({ type: 'load_anchor', channel: 'session', anchor_id: anchorId });
  }

  /** 念头注入（ImpulseBar → sim player_impulse；批次 A）。
   *  客户端预校验：空白/超长即本地拒（不发帧、置 impulseError）；
   *  服务端 impulse_gate 拒收经 error 帧（ref=player_impulse）回同一 UI 位。 */
  sendImpulse(text: string): void {
    const store = useUiStore.getState();
    const cleaned = text.trim();
    if (!cleaned) {
      store.setImpulseError('念头还没成形。');
      return;
    }
    if (cleaned.length > IMPULSE_MAX_LEN) {
      store.setImpulseError(IMPULSE_TOO_LONG_MSG);
      return;
    }
    this.ws?.send({ type: 'player_impulse', channel: 'control', text: cleaned });
  }
}

export const runtime = new Runtime();

// D11：session_state 帧的 speed/paused 权威消费（ws.ts 不直接依赖 store——
// 经 sink 注入；重连/读档后 TopBar 与服务端真实状态对齐）。
setControlStateSink((speed, paused) => {
  const store = useUiStore.getState();
  if (speed !== null) store.setSpeed(speed as Speed);
  if (paused !== null) store.setPaused(paused);
});
