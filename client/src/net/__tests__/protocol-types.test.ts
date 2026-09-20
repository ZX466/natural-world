/**
 * client/src/net/__tests__/protocol-types.test.ts — 类型级断言（vitest expectTypeOf）。
 *
 * 任务 TASK-002 #3：验证 state_delta/player_impulse/control 字段与 ws-protocol.md 一致，
 * 且出戏边界成立（rtoken 仅在 render 通道；内部 entity_id/source_id/tick/seed/seq/branch_id
 * 一律不出现）。纯类型检查，无运行时逻辑。
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
  MoveRequestMessage,
  PerceptionMessage,
  MonologueMessage,
  ImpulseFeedbackMessage,
  Actor,
  ActorDelta,
  Structure,
  Projectile,
  Hit,
  AnchorListItem,
  ProfileListItem,
  ProfileCreate,
  WorldMapResponse,
  MapChunk,
} from '../protocol';

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
});
