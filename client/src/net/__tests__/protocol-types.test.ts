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
  PerceptionMessage,
  MonologueMessage,
  Actor,
  ActorDelta,
  Structure,
  Projectile,
  Hit,
  AnchorListItem,
  ProfileListItem,
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
});
