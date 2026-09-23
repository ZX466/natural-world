/**
 * client/src/net/__tests__/protocol-types.test.ts — 类型级断言（vitest expectTypeOf）。
 *
 * 任务 TASK-002 #3：验证 state_delta/player_impulse/control 字段与 ws-protocol.md 一致，
 * 且出戏边界成立（rtoken 仅在 render 通道；内部 entity_id/source_id/tick/seed/seq/branch_id
 * 一律不出现）。纯类型检查，无运行时逻辑。
 *
 * K04 扩展（2026-09-21）：WS 消息类型全量生成后，对 `WsMessage` 判别联合本身断言——
 * 消息 type 枚举与 ws-protocol.md §3 清单逐条对齐（C→S 5 + S→C 9，共 14 个成员），
 * 且每个成员的必填字段形状在位（判别键 + 信封 + 通道）。
 *
 * 说明：任务文档写 "move_intent"，DESIGN.md §6 的 Intent 是 LLM 内部输出、非客户端消息；
 * 玩家唯一主动动作是念头注入（player_impulse，见 ws-protocol.md §3.1）——按已批协议实现，
 * 此处对 player_impulse 断言。rtoken 已由 Claude 评审批准为「不透明替身」（前端永不接触真实 id），
 * 故本测试断言真实内部 id 缺席、rtoken 仅 render 通道出现。
 */
import { describe, it, expectTypeOf } from 'vitest';
import type {
  WsMessage,
  StateDeltaMessage,
  FullSnapshotMessage,
  PlayerImpulseMessage,
  SetControlMessage,
  LoadAnchorMessage,
  SyncRequestMessage,
  MoveRequestMessage,
  PerceptionMessage,
  MonologueMessage,
  ImpulseFeedbackMessage,
  CombatEventMessage,
  TimescaleMessage,
  ControlAckMessage,
  WsErrorMessage,
  Actor,
  ActorDelta,
  Structure,
  Projectile,
  Hit,
  AnchorListItem,
  ProfileListItem,
  ProfileCreate,
  ProfileUpdate,
  WorldMapResponse,
  MapChunk,
} from '../protocol';
import type { paths } from '@shared/protocol';

describe('ws-protocol 类型与出戏边界', () => {
  it('state_delta 字段与 ws-protocol.md 一致；用 ws_seq 而非 tick', () => {
    expectTypeOf<StateDeltaMessage>().toHaveProperty('ws_seq');
    expectTypeOf<StateDeltaMessage>().toHaveProperty('actors');
    expectTypeOf<StateDeltaMessage['channel']>().toEqualTypeOf<'render'>();
    expectTypeOf<StateDeltaMessage['type']>().toEqualTypeOf<'state_delta'>();
    expectTypeOf<ActorDelta>().toHaveProperty('rtoken'); // 替身存在
    // full_snapshot（M0 渲染闭环全量）：同样以 rtoken 标识、无世界真相字段
    expectTypeOf<FullSnapshotMessage['type']>().toEqualTypeOf<'full_snapshot'>();
    expectTypeOf<FullSnapshotMessage['actors']>().toMatchTypeOf<readonly Actor[]>();
    expectTypeOf<FullSnapshotMessage>().not.toHaveProperty('tick');
    expectTypeOf<FullSnapshotMessage>().not.toHaveProperty('seed');
    // 出戏边界：tick/seed/seq/entity_id 一律缺席
    expectTypeOf<StateDeltaMessage>().not.toHaveProperty('tick');
    expectTypeOf<StateDeltaMessage>().not.toHaveProperty('seed');
    expectTypeOf<StateDeltaMessage>().not.toHaveProperty('seq');
    expectTypeOf<StateDeltaMessage>().not.toHaveProperty('entity_id');
  });

  it('player_impulse / set_control 字段与 ws-protocol.md 一致', () => {
    expectTypeOf<PlayerImpulseMessage['channel']>().toEqualTypeOf<'control'>();
    expectTypeOf<PlayerImpulseMessage['type']>().toEqualTypeOf<'player_impulse'>();
    expectTypeOf<PlayerImpulseMessage>().toHaveProperty('text');
    expectTypeOf<SetControlMessage['type']>().toEqualTypeOf<'set_control'>();
    expectTypeOf<SetControlMessage['action']>().toEqualTypeOf<'pause' | 'resume' | 'set_speed'>();
    expectTypeOf<SetControlMessage>().not.toHaveProperty('tick');
  });

  it('move_request：目标必须是整数格坐标，无 rtoken', () => {
    expectTypeOf<MoveRequestMessage['channel']>().toEqualTypeOf<'render'>();
    expectTypeOf<MoveRequestMessage['type']>().toEqualTypeOf<'move_request'>();
    // target_x / target_y 必须是整数（格坐标），非浮点/字符串
    expectTypeOf<MoveRequestMessage['target_x']>().toEqualTypeOf<number>();
    expectTypeOf<MoveRequestMessage['target_y']>().toEqualTypeOf<number>();
    expectTypeOf<MoveRequestMessage['target_x']>().toMatchTypeOf<number>();
    expectTypeOf<MoveRequestMessage>().not.toMatchTypeOf<{ target_x: string }>();
    expectTypeOf<MoveRequestMessage>().not.toMatchTypeOf<{
      target_x: number;
      target_y: number;
      target_z: number;
    }>();
    // 客户端只发目标格，无 rtoken（服务端知道主角是谁）
    expectTypeOf<MoveRequestMessage>().not.toHaveProperty('rtoken');
    expectTypeOf<MoveRequestMessage>().not.toHaveProperty('entity_id');
    // 属于 WsMessage 判别联合
    expectTypeOf<MoveRequestMessage>().toMatchTypeOf<WsMessage>();
  });

  it('WsMessage 是判别联合，按 type 收窄', () => {
    expectTypeOf<StateDeltaMessage>().toMatchTypeOf<WsMessage>(); // 成员属于联合
    const m = {} as WsMessage;
    if (m.type === 'state_delta') {
      expectTypeOf(m).toEqualTypeOf<StateDeltaMessage>(); // 收窄成功
    }
    if (m.type === 'player_impulse') {
      expectTypeOf(m).toEqualTypeOf<PlayerImpulseMessage>();
    }
  });

  it('出戏边界：内部 id/世界真相缺席；rtoken 仅 render 通道', () => {
    // render 子结构用 rtoken 替身
    expectTypeOf<Actor>().toHaveProperty('rtoken');
    expectTypeOf<Structure>().toHaveProperty('rtoken');
    expectTypeOf<Projectile>().toHaveProperty('rtoken');
    expectTypeOf<Hit>().toHaveProperty('rtoken');
    // 真实内部 id 在 render 子结构缺席
    expectTypeOf<Actor>().not.toHaveProperty('entity_id');
    expectTypeOf<Actor>().not.toHaveProperty('source_id');
    // rtoken 不泄漏进 narrative 通道（玩家读到的文本里无替身/系统词）
    expectTypeOf<PerceptionMessage>().not.toHaveProperty('rtoken');
    expectTypeOf<MonologueMessage>().not.toHaveProperty('rtoken');
    expectTypeOf<PerceptionMessage>().not.toHaveProperty('tick');
    expectTypeOf<MonologueMessage>().not.toHaveProperty('tick');
  });

  it('HTTP meta shell：anchor 不回传原始 tick/seq；profile 不回传 api_key 明文', () => {
    expectTypeOf<AnchorListItem>().toHaveProperty('story_label'); // 叙事标签，非 tick
    expectTypeOf<AnchorListItem>().not.toHaveProperty('tick');
    expectTypeOf<AnchorListItem>().not.toHaveProperty('seq');
    expectTypeOf<AnchorListItem>().not.toHaveProperty('seed');
    expectTypeOf<AnchorListItem>().not.toHaveProperty('branch_id');
    expectTypeOf<ProfileListItem>().toHaveProperty('api_key_hint'); // 仅掩码
    expectTypeOf<ProfileListItem>().not.toHaveProperty('api_key'); // 明文永不回传
  });

  it('K02 #1 /api/world/map：chunk 模式、仅静态资产（无 seed/tick/entity_id）', () => {
    expectTypeOf<WorldMapResponse>().toHaveProperty('w');
    expectTypeOf<WorldMapResponse>().toHaveProperty('h');
    expectTypeOf<WorldMapResponse>().toHaveProperty('tileset');
    expectTypeOf<WorldMapResponse['chunks']>().toMatchTypeOf<readonly MapChunk[]>();
    // chunk：cx/cy 整数 + collision_b64（base64 字符串）
    expectTypeOf<MapChunk['cx']>().toEqualTypeOf<number>();
    expectTypeOf<MapChunk['cy']>().toEqualTypeOf<number>();
    expectTypeOf<MapChunk['collision_b64']>().toEqualTypeOf<string>();
    // 出戏边界：静态资产不含世界真相
    expectTypeOf<MapChunk>().not.toHaveProperty('seed');
    expectTypeOf<MapChunk>().not.toHaveProperty('tick');
    expectTypeOf<MapChunk>().not.toHaveProperty('entity_id');
    expectTypeOf<WorldMapResponse>().not.toHaveProperty('seed');
  });

  it('K02 #2 M1 三消息：content 为第一人称字符串、无数值/系统字段', () => {
    // perception：sense 五通道 + content（第一人称叙事）
    expectTypeOf<PerceptionMessage['type']>().toEqualTypeOf<'perception'>();
    expectTypeOf<PerceptionMessage['channel']>().toEqualTypeOf<'narrative'>();
    expectTypeOf<PerceptionMessage['sense']>().toEqualTypeOf<
      'sight' | 'sound' | 'smell' | 'touch' | 'interoception'
    >();
    expectTypeOf<PerceptionMessage['content']>().toEqualTypeOf<string>();
    // monologue：三形态 + content（W7：删除戏外 anchor_ref）
    expectTypeOf<MonologueMessage['form']>().toEqualTypeOf<'bubble' | 'thought' | 'plan'>();
    expectTypeOf<MonologueMessage['content']>().toEqualTypeOf<string>();
    expectTypeOf<MonologueMessage>().not.toHaveProperty('anchor_ref');
    // impulse_feedback：cue 表现提示（W7：删除数值 delay_ms）
    expectTypeOf<ImpulseFeedbackMessage['cue']>().toEqualTypeOf<
      'accepted' | 'hesitation' | 'complaint' | 'resistance'
    >();
    expectTypeOf<ImpulseFeedbackMessage>().toHaveProperty('reaction_monologue');
    expectTypeOf<ImpulseFeedbackMessage>().not.toHaveProperty('delay_ms');
    // content 一律是字符串，且不携带数值型世界真相字段
    expectTypeOf<ImpulseFeedbackMessage>().not.toHaveProperty('conflict');
    expectTypeOf<PerceptionMessage>().not.toHaveProperty('salience');
    expectTypeOf<PerceptionMessage>().not.toHaveProperty('uncertainty');
  });

  it('K02 #3 settings/profiles：K5 白名单、无 api_key/provider/params', () => {
    // 响应白名单（codex K5）：绝不含 api_key 明文
    expectTypeOf<ProfileListItem>().toHaveProperty('api_key_hint');
    expectTypeOf<ProfileListItem>().not.toHaveProperty('api_key');
    expectTypeOf<ProfileListItem>().not.toHaveProperty('api_key_enc');
    // 与 sim LLMProfile 表对齐：扁平 temperature/max_tokens，无 provider/params
    expectTypeOf<ProfileListItem>().toHaveProperty('temperature');
    expectTypeOf<ProfileListItem>().toHaveProperty('max_tokens');
    expectTypeOf<ProfileListItem>().toHaveProperty('active');
    expectTypeOf<ProfileListItem>().not.toHaveProperty('provider');
    expectTypeOf<ProfileListItem>().not.toHaveProperty('params');
    // 创建请求：api_key 明文入（后端即加密落库）
    expectTypeOf<ProfileCreate>().toHaveProperty('api_key');
    expectTypeOf<ProfileCreate>().not.toHaveProperty('provider');
    expectTypeOf<ProfileCreate>().not.toHaveProperty('params');
  });

  it('K03 #1 ProfileListItem 与 sim 实际响应一致（8 字段，实测回包对齐）', () => {
    // sim POST /api/settings/profiles 实测回包键：
    // {id,name,base_url,model,temperature,max_tokens,active,api_key_hint}
    expectTypeOf<ProfileListItem>().toHaveProperty('id');
    expectTypeOf<ProfileListItem>().toHaveProperty('name');
    expectTypeOf<ProfileListItem>().toHaveProperty('base_url');
    expectTypeOf<ProfileListItem>().toHaveProperty('model');
    expectTypeOf<ProfileListItem['temperature']>().toEqualTypeOf<number>();
    expectTypeOf<ProfileListItem['max_tokens']>().toEqualTypeOf<number>();
    expectTypeOf<ProfileListItem['active']>().toEqualTypeOf<boolean>();
    expectTypeOf<ProfileListItem['api_key_hint']>().toEqualTypeOf<string>();
    // 不泄漏密钥与内部列
    expectTypeOf<ProfileListItem>().not.toHaveProperty('api_key');
    expectTypeOf<ProfileListItem>().not.toHaveProperty('api_key_enc');
    expectTypeOf<ProfileListItem>().not.toHaveProperty('is_active'); // sim 用 active
  });

  it('K03 #2 ProfileCreate 与 sim 约束一致（name 1–64 / temperature 0–2 / max_tokens 1–32768）', () => {
    expectTypeOf<ProfileCreate>().toHaveProperty('name');
    expectTypeOf<ProfileCreate>().toHaveProperty('base_url');
    expectTypeOf<ProfileCreate>().toHaveProperty('model');
    expectTypeOf<ProfileCreate>().toHaveProperty('api_key'); // 明文入，后端加密
    expectTypeOf<ProfileCreate>().toHaveProperty('temperature'); // 可选（默认 0.7）
    expectTypeOf<ProfileCreate>().toHaveProperty('max_tokens'); // 可选（默认 2048）
    expectTypeOf<ProfileCreate['name']>().toEqualTypeOf<string>();
    // 与 sim settings.py::ProfileCreate 对齐：无 provider/params
    expectTypeOf<ProfileCreate>().not.toHaveProperty('provider');
    expectTypeOf<ProfileCreate>().not.toHaveProperty('params');
  });

  it('K03 #3 ProfileUpdate 全字段可选且可显式置 null（对齐 sim pydantic str | None）', () => {
    // sim settings.py::ProfileUpdate 六字段均 `T | None = None` 且无必填项，
    // openapi-typescript 产出 `?(T | null)`（可选 + 联合含 null）。
    // 逐字段断言「值域含 null」，比整物体形状更耐 future 加字段。
    expectTypeOf<ProfileUpdate['name']>().toEqualTypeOf<string | null | undefined>();
    expectTypeOf<ProfileUpdate['base_url']>().toEqualTypeOf<string | null | undefined>();
    expectTypeOf<ProfileUpdate['model']>().toEqualTypeOf<string | null | undefined>();
    expectTypeOf<ProfileUpdate['api_key']>().toEqualTypeOf<string | null | undefined>();
    expectTypeOf<ProfileUpdate['temperature']>().toEqualTypeOf<number | null | undefined>();
    expectTypeOf<ProfileUpdate['max_tokens']>().toEqualTypeOf<number | null | undefined>();
    // 更新为白名单外字段一律不存在（防前端臆造 sim 不认的键）
    expectTypeOf<ProfileUpdate>().not.toHaveProperty('provider');
    expectTypeOf<ProfileUpdate>().not.toHaveProperty('params');
    expectTypeOf<ProfileUpdate>().not.toHaveProperty('id');
  });

  it('K03 #4 settings 路径参数名为 profile_id（与 sim 路由签名逐字对齐）', () => {
    // 快照侧曾用 {id} 而 sim 函数签名是 profile_id → 归一为 {profile_id}。
    // 前端 settingsApi.ts 用 encodeURIComponent(id) 拼 URL，参数名不影响调用，
    // 但 paths 类型是自文档契约，必须与 sim 一致。
    type Update = NonNullable<
      paths['/api/settings/profiles/{profile_id}']['patch']
    >;
    type Activate = NonNullable<
      paths['/api/settings/profiles/{profile_id}/activate']['post']
    >;
    expectTypeOf<NonNullable<Update['parameters']['path']['profile_id']>>().toEqualTypeOf<string>();
    expectTypeOf<NonNullable<Activate['parameters']['path']['profile_id']>>().toEqualTypeOf<string>();
    // 旧名 id 必须已从 paths 中消失
    expectTypeOf<paths>().not.toHaveProperty('/api/settings/profiles/{id}');
    expectTypeOf<paths>().not.toHaveProperty('/api/settings/profiles/{id}/activate');
  });

  it('K03 #5 anchors 路径参数名为 anchor_id（M5-K2 裁 5，与 settings 同逻辑）', () => {
    // anchors 是 M5 新路由：快照曾用 {id}，因 K3 已将 settings 归一为 {profile_id}，
    // 采同逻辑一次做对 → {anchor_id}。sim/api/anchors.py 形参名必须逐字为 anchor_id。
    type Rename = NonNullable<paths['/api/anchors/{anchor_id}']['patch']>;
    type Delete = NonNullable<paths['/api/anchors/{anchor_id}']['delete']>;
    expectTypeOf<NonNullable<Rename['parameters']['path']['anchor_id']>>().toEqualTypeOf<string>();
    expectTypeOf<NonNullable<Delete['parameters']['path']['anchor_id']>>().toEqualTypeOf<string>();
    // 旧名 id 必须已从 anchors paths 中消失（旧路径整个模板亦不存在）
    expectTypeOf<paths>().not.toHaveProperty('/api/anchors/{id}');
  });

  // ── K04：WsMessage 判别联合（gen-protocol 全量生成后）──────────────────
  it('K04 #1 WsMessage 判别联合：type 枚举 = ws-protocol.md §3 清单（C→S 5 + S→C 9）', () => {
    // §3.1 client → sim（5 条：含玩家点击寻路 move_request）
    expectTypeOf<PlayerImpulseMessage['type']>().toEqualTypeOf<'player_impulse'>();
    expectTypeOf<SetControlMessage['type']>().toEqualTypeOf<'set_control'>();
    expectTypeOf<LoadAnchorMessage['type']>().toEqualTypeOf<'load_anchor'>();
    expectTypeOf<MoveRequestMessage['type']>().toEqualTypeOf<'move_request'>();
    expectTypeOf<SyncRequestMessage['type']>().toEqualTypeOf<'sync_request'>();
    // §3.2 sim → client（9 条）
    expectTypeOf<FullSnapshotMessage['type']>().toEqualTypeOf<'full_snapshot'>();
    expectTypeOf<StateDeltaMessage['type']>().toEqualTypeOf<'state_delta'>();
    expectTypeOf<PerceptionMessage['type']>().toEqualTypeOf<'perception'>();
    expectTypeOf<MonologueMessage['type']>().toEqualTypeOf<'monologue'>();
    expectTypeOf<ImpulseFeedbackMessage['type']>().toEqualTypeOf<'impulse_feedback'>();
    expectTypeOf<CombatEventMessage['type']>().toEqualTypeOf<'combat_event'>();
    expectTypeOf<TimescaleMessage['type']>().toEqualTypeOf<'timescale'>();
    expectTypeOf<ControlAckMessage['type']>().toEqualTypeOf<'control_ack'>();
    expectTypeOf<WsErrorMessage['type']>().toEqualTypeOf<'error'>();
    // 联合判别键：WsMessage['type'] 恰为上述 14 个枚举值（缺一即漏消息，多一即野消息）
    expectTypeOf<WsMessage['type']>().toEqualTypeOf<
      | 'player_impulse'
      | 'set_control'
      | 'load_anchor'
      | 'move_request'
      | 'sync_request'
      | 'full_snapshot'
      | 'state_delta'
      | 'perception'
      | 'monologue'
      | 'impulse_feedback'
      | 'combat_event'
      | 'timescale'
      | 'control_ack'
      | 'error'
    >();
    // 判别键存在且为 string 字面量联合（openapi-typescript discriminator 生成前提）
    expectTypeOf<WsMessage>().toHaveProperty('type');
    // 出戏边界：hello/hello_ack 是 W6 鉴权握手层（安全域），不进游戏协议清单
    expectTypeOf<WsMessage['type']>().not.toEqualTypeOf<'hello'>();
    expectTypeOf<WsMessage['type']>().not.toEqualTypeOf<'hello_ack'>();
  });

  it('K04 #2 WsMessage 成员必填字段形状：信封 v/ws_seq + 通道判别 + 消息特有键', () => {
    // 信封公共必填：所有成员都带 v（协议版本）+ ws_seq（传输序号，非 tick）
    expectTypeOf<FullSnapshotMessage>().toHaveProperty('v');
    expectTypeOf<FullSnapshotMessage>().toHaveProperty('ws_seq');
    expectTypeOf<StateDeltaMessage>().toHaveProperty('v');
    expectTypeOf<StateDeltaMessage>().toHaveProperty('ws_seq');
    expectTypeOf<PlayerImpulseMessage>().toHaveProperty('v');
    expectTypeOf<PlayerImpulseMessage>().toHaveProperty('ws_seq');
    // C→S 特有必填
    expectTypeOf<SetControlMessage>().toHaveProperty('action');
    expectTypeOf<LoadAnchorMessage>().toHaveProperty('anchor_id');
    expectTypeOf<SyncRequestMessage>().toHaveProperty('reason');
    // S→C 特有必填（M1 叙事/控制 + M4 战斗）
    expectTypeOf<PerceptionMessage>().toHaveProperty('sense');
    expectTypeOf<PerceptionMessage>().toHaveProperty('content');
    expectTypeOf<MonologueMessage>().toHaveProperty('form');
    expectTypeOf<MonologueMessage>().toHaveProperty('content');
    expectTypeOf<ImpulseFeedbackMessage>().toHaveProperty('injected');
    expectTypeOf<ImpulseFeedbackMessage>().toHaveProperty('cue');
    expectTypeOf<ImpulseFeedbackMessage>().toHaveProperty('reaction_monologue');
    expectTypeOf<CombatEventMessage>().toHaveProperty('exchange');
    expectTypeOf<CombatEventMessage>().toHaveProperty('rtoken');
    expectTypeOf<TimescaleMessage>().toHaveProperty('mode');
    expectTypeOf<TimescaleMessage>().toHaveProperty('active');
    expectTypeOf<ControlAckMessage>().toHaveProperty('action');
    expectTypeOf<ControlAckMessage>().toHaveProperty('applied');
    expectTypeOf<WsErrorMessage>().toHaveProperty('ref');
    expectTypeOf<WsErrorMessage>().toHaveProperty('code');
    expectTypeOf<WsErrorMessage>().toHaveProperty('message');
    // 通道判别字面量（render/narrative/control/session/error 五通道契约）
    expectTypeOf<FullSnapshotMessage['channel']>().toEqualTypeOf<'render'>();
    expectTypeOf<StateDeltaMessage['channel']>().toEqualTypeOf<'render'>();
    expectTypeOf<CombatEventMessage['channel']>().toEqualTypeOf<'render'>();
    expectTypeOf<PerceptionMessage['channel']>().toEqualTypeOf<'narrative'>();
    expectTypeOf<MonologueMessage['channel']>().toEqualTypeOf<'narrative'>();
    expectTypeOf<PlayerImpulseMessage['channel']>().toEqualTypeOf<'control'>();
    expectTypeOf<SetControlMessage['channel']>().toEqualTypeOf<'control'>();
    expectTypeOf<ImpulseFeedbackMessage['channel']>().toEqualTypeOf<'control'>();
    expectTypeOf<TimescaleMessage['channel']>().toEqualTypeOf<'control'>();
    expectTypeOf<ControlAckMessage['channel']>().toEqualTypeOf<'control'>();
    expectTypeOf<LoadAnchorMessage['channel']>().toEqualTypeOf<'session'>();
    expectTypeOf<SyncRequestMessage['channel']>().toEqualTypeOf<'session'>();
    expectTypeOf<WsErrorMessage['channel']>().toEqualTypeOf<'error'>();
    // 出戏边界：任何 WS 载荷都不含世界真相 id/tick/seed
    expectTypeOf<WsMessage>().not.toHaveProperty('tick');
    expectTypeOf<WsMessage>().not.toHaveProperty('seed');
    expectTypeOf<WsMessage>().not.toHaveProperty('entity_id');
    expectTypeOf<WsMessage>().not.toHaveProperty('source_id');
    expectTypeOf<WsMessage>().not.toHaveProperty('branch_id');
  });
});
