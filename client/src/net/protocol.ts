/**
 * client/src/net/protocol.ts — 前端唯一协议类型入口（DESIGN.md §5 / m0-client.md §2）。
 *
 * - shared/protocol.ts 是 openapi-typescript 生成物（永不手写，见 docs/api/codegen.md）。
 * - 本文件只 re-export 生成物 + 组合 WS 判别联合别名；不改写、不新增字段。
 * - WS 消息与 HTTP 端点类型一并落在 shared/protocol.ts 的 components["schemas"]。
 */
export type * from '@shared/protocol';
import type { components } from '@shared/protocol';

type Schemas = components['schemas'];

/** WS 消息判别联合：按 msg.type 收窄（见 ws-protocol.md §3）。 */
export type WsMessage = Schemas['WsMessage'];

// ── client → sim ───────────────────────────────────────────────
/** 念头注入（玩家唯一主动动作，M4）。注：DESIGN.md 里 Intent 是 LLM 内部输出（§6），
 *  非客户端消息；玩家只发念头。任务文档中的 "move_intent" 即此消息的别名。 */
export type PlayerImpulseMessage = Schemas['PlayerImpulseMessage'];
/** 暂停/倍速（1x/4x/16x）；战斗时间尺由 sim 自动切，不可客户端设。 */
export type SetControlMessage = Schemas['SetControlMessage'];
export type LoadAnchorMessage = Schemas['LoadAnchorMessage'];
/** 玩家点击寻路：客户端只发目标格坐标，sim 寻路并驱动主角；无 rtoken。 */
export type MoveRequestMessage = Schemas['MoveRequestMessage'];
export type SyncRequestMessage = Schemas['SyncRequestMessage'];

// ── sim → client ───────────────────────────────────────────────
export type FullSnapshotMessage = Schemas['FullSnapshotMessage'];
export type StateDeltaMessage = Schemas['StateDeltaMessage'];
export type PerceptionMessage = Schemas['PerceptionMessage'];
export type MonologueMessage = Schemas['MonologueMessage'];
export type ImpulseFeedbackMessage = Schemas['ImpulseFeedbackMessage'];
export type CombatEventMessage = Schemas['CombatEventMessage'];
export type TimescaleMessage = Schemas['TimescaleMessage'];
export type ControlAckMessage = Schemas['ControlAckMessage'];
export type WsErrorMessage = Schemas['WsErrorMessage'];

// ── render 子结构（含 rtoken 不透明替身）──────────────────────
export type Actor = Schemas['Actor'];
export type ActorDelta = Schemas['ActorDelta'];
export type Structure = Schemas['Structure'];
export type Projectile = Schemas['Projectile'];
export type Hit = Schemas['Hit'];
export type RToken = Schemas['RToken'];

// ── HTTP（戏外 meta shell）──────────────────────────────────────
export type ProfileCreate = Schemas['ProfileCreate'];
export type ProfileListItem = Schemas['ProfileListItem'];
export type AnchorListItem = Schemas['AnchorListItem'];
export type AnchorCreate = Schemas['AnchorCreate'];
export type HealthStatus = Schemas['HealthStatus'];
