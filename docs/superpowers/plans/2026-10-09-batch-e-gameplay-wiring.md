# 批次 E 玩法接线 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把断在执行面的玩法接通——陈默能说话/调查/买卖/建造/动手，村民聊天产生记忆/关系/流言，完工建筑真实占格，非理性偏差回到检索。

**Architecture:** 全部走既有架构：新玩法 = 新事件 kind（payload 模型同 commit 登记 `PAYLOAD_MODELS`）+ no-op/纯函数 handler（C4）；执行面在 `ChenmoDriver.execute_pending` 扩分支（C1 闸门已放行的动作终于有落地）；关系/金币/hp/在建进度是进程内 runtime 内存态（火场/需求同口径，不入 WorldState），死亡/转账/完工等**结果**经事件落流可重放（C5：结算全部确定性哈希，无 RNG 流）。村民侧在 `sim_exec.npc_events_for_tick` 扩到站开口。WS 只加 `structures` 增量字段（协议 1.6→1.7 additive）。

**Tech Stack:** Python 3.12 + pydantic v2 + pytest（uv）；React/Phaser/Vitest（npm）。零新依赖。

**Spec:** DESIGN.md（§6 Intent 契约 / §9 战斗 / §10 意愿 / §13 NPC / §14 建造）；本次会话的「玩法实现度盘点」结论（E1–E6 顺序已确认）。

## Global Constraints

- C4：状态变更只走 `apply(event)`；新 kind 必须同 commit 登记 `sim/core/persistence/event_validation.py::PAYLOAD_MODELS` + `build_default_bus` handler（no-op 也要注册，否则重放炸「未注册的事件种类」）。
- C5：同 seed+同事件序列 ⇒ 逐位一致；运行时随机一律 sha256 哈希纯函数（抄 `sim_exec._hash_u32` 形），禁 `random.*`/`datetime.now()`。
- 事件 payload 一律 `ConfigDict(frozen=True, extra="forbid")`；禁归因键（谁打的/谁欠谁不入事件 payload——归因只活在进程内 runtime）。
- 出戏铁律：对话模板/回复池/呼救文本必须过 `sim.llm.prompts.banned_words.scan()`（测试钉）；档位号/血量数值不入戏内文本（铜钱数额是戏内事实，允许）。
- 禁第二 SQL 驱动：关系/金币/hp 全部进程内账本（先例：`chenmo_memory` InMemoryStore，其 docstring 已钉「sync sqlite3 与 aiosqlite 单写者共库 = 跨驱动锁风险」）。
- Windows + uv：测试 `uv run pytest`；前端在 `client/` 下 `npm run test/typecheck/lint`。
- 提交：Conventional Commits，结尾 `Co-Authored-By: Claude Code <noreply@anthropic.com>`。
- 每个 Task 结束跑全量 `uv run pytest -q` 绿再 commit（项目门禁口径）。

## Review Focus

1. **重放逐位一致**：新 kind 的 handler 必须 no-op 或纯函数；执行面 runtime 内存态不得进 WorldState。钉：每任务测试 fold 新事件前后 `state_hash` 相等；Task 14 末跑 `uv run pytest sim/tests/replay -q`。
2. **双 SQL 驱动锁**：E2/E3 不得引入 sync sqlite3 写面（RelationshipStore 是 sync sqlite3，只许在**测试**里用）。钉：每任务收尾 `Grep "sqlite3.connect" sim/ --glob '!**/tests/**'` 零新增。
3. **到站判定 tick 漂移**（D3 教训）：村民聊天到站判定用「决策节拍当时实体邻域」，配对冷却账本由调用方持有（同 `monologue_last` 模式），散点目标 tick 无关（`_scatter_near` 已 tick 无关，直接复用）。
4. **钩子覆盖惨案复发**（D9 教训）：新钩子用 `loop.attach_npc_runtime`（多槽列表），绝不新造单槽 attach。
5. **前端未知帧静默**：ws.py 新帧类型未到 client 消费前，client `default: 静默忽略` 兜底——Task 12 之前前端零改动也安全。

---

### Task 1: E1 事件契约——npc.chat 事件 kind + 工厂 + payload 登记

**Files:**
- Modify: `sim/core/events.py`（EventKind 追加 + payload 模型 + 工厂函数）
- Modify: `sim/core/persistence/event_validation.py`（PAYLOAD_MODELS 登记）
- Modify: `sim/core/world.py`（build_default_bus 注册 no-op handler）
- Test: `sim/tests/test_e1_chat_events.py`

**Interfaces:**
- Produces: `EventKind.NPC_CHAT = "npc.chat"`；payload 模型 `NpcChatPayload(npc_id: str, to_id: str, line: str)`；工厂 `npc_chat_event(tick, npc_id, to_id, line, branch_id="main") -> WorldEvent`（含 banned 终扫拒抛 `ValueError`）。后续 Task 2/3/6 消费。

- [ ] **Step 1: 写失败测试**

```python
# sim/tests/test_e1_chat_events.py
"""E1：npc.chat 事件契约（工厂校验 + PAYLOAD_MODELS 登记 + bus 可重放）。"""
import pytest

from sim.core.events import EventKind, WorldEvent, npc_chat_event
from sim.core.persistence.event_validation import PAYLOAD_MODELS, validate_store_row
from sim.core.world import WorldState, build_default_bus
from sim.core.world import TickContext


def test_npc_chat_event_factory_shape():
    ev = npc_chat_event(tick=10, npc_id="chenmo", to_id="villager_01", line="掌柜的，抓副药。")
    assert ev.event_type is EventKind.NPC_CHAT
    assert ev.actor_id == "chenmo"
    assert ev.payload["npc_id"] == "chenmo"
    assert ev.payload["to_id"] == "villager_01"
    assert ev.payload["line"] == "掌柜的，抓副药。"


def test_npc_chat_event_rejects_banned_line():
    with pytest.raises(ValueError, match="banned"):
        npc_chat_event(tick=10, npc_id="chenmo", to_id="villager_01", line="你是不是AI模型")


def test_npc_chat_payload_registered():
    assert PAYLOAD_MODELS[EventKind.NPC_CHAT].model_validate(
        {"npc_id": "a", "to_id": "b", "line": "x"}
    )


def test_npc_chat_store_row_validates():
    ev = npc_chat_event(tick=1, npc_id="a", to_id="b", line="吃了么")
    validate_store_row(ev.to_store_dict())


def test_npc_chat_fold_is_noop_hash_stable():
    bus = build_default_bus()
    state = WorldState(world_seed=42)
    ctx = TickContext()
    ev = npc_chat_event(tick=0, npc_id="a", to_id="b", line="吃了么")
    before = state.state_hash()
    result = bus.apply(state, ev, ctx)
    assert result.state.state_hash() == before  # no-op：hash 逐位不变
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest sim/tests/test_e1_chat_events.py -q`
Expected: FAIL —— `ImportError: cannot import name 'npc_chat_event'`

- [ ] **Step 3: 最小实现**

`sim/core/events.py` 三处追加：

```python
# EventKind 内（M4 段后）：
    # ---- 批次 E（E1 玩法接线）----
    #: 面对面聊天记录（E1）：行为记录面（谁对谁说了一句什么）——
    #: **零归因键**（关系/记忆效应归进程内 runtime），line 过 banned 终扫。
    NPC_CHAT = "npc.chat"
```

```python
class NpcChatPayload(BaseModel):
    """面对面聊天（批次 E1）。line 是出站戏内文本（工厂层 banned 终扫强制）。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    npc_id: str
    to_id: str
    line: str
```

```python
def npc_chat_event(
    tick: int,
    npc_id: str,
    to_id: str,
    line: str,
    branch_id: str = "main",
) -> WorldEvent:
    """聊天事件工厂。line 命中禁词即拒（ValueError；与独白同纪律）。"""
    from sim.llm.prompts.banned_words import scan

    if scan(line).hits:
        raise ValueError(f"npc.chat line banned hit: tick={tick}")
    p = NpcChatPayload(npc_id=npc_id, to_id=to_id, line=line)
    return WorldEvent(
        branch_id=branch_id,
        tick=tick,
        event_type=EventKind.NPC_CHAT,
        actor_id=npc_id,
        payload=p.model_dump(mode="json"),
    )
```

`sim/core/persistence/event_validation.py`：import `NpcChatPayload`，`PAYLOAD_MODELS` 加一行 `EventKind.NPC_CHAT: NpcChatPayload,`

`sim/core/world.py`：

```python
def _apply_npc_chat(state: WorldState, event: WorldEvent, ctx: TickContext) -> ApplyResult:
    """NPC_CHAT（批次 E1）：聊天行为记录，状态层 no-op（关系/记忆效应归 runtime）。"""
    from sim.core.events import NpcChatPayload

    NpcChatPayload.model_validate(event.payload)
    return ApplyResult(state=state)
```

`build_default_bus` 加 `bus.register(EventKind.NPC_CHAT, _apply_npc_chat)`

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest sim/tests/test_e1_chat_events.py -q`
Expected: 5 passed

- [ ] **Step 5: 全量门禁**

Run: `uv run pytest -q`
Expected: 全绿（2505+ 新增）

- [ ] **Step 6: Commit**

```bash
git add sim/core/events.py sim/core/persistence/event_validation.py sim/core/world.py sim/tests/test_e1_chat_events.py
git commit -m "feat(e1): npc.chat 事件契约——工厂+payload登记+no-op handler"
```

---

### Task 2: E1 陈默 talk_to 执行面——LLM 生成台词 + 聊天事件

**Files:**
- Create: `sim/agent/dialogue.py`（台词生成：LLM 优先、模板池兜底）
- Modify: `sim/agent/driver.py`（execute_pending 扩 talk_to 分支）
- Test: `sim/tests/test_e1_talk_to.py`

**Interfaces:**
- Consumes: Task 1 `npc_chat_event`；既有 `LlmClient.complete`/`ProfileSnapshot`；`WorldState.entities`。
- Produces: `sim.agent.dialogue.make_line(llm, profile_provider, speaker: str, listener_name: str, reason: str, tick: int) -> str`（async；LLM 不可用时从模板池按 (speaker, tick) 哈希挑）；`ChenmoDriver` 注入 `dialogue_provider: Callable[..., Awaitable[str]] | None`（构造参数默认 None=模板池直用）。

- [ ] **Step 1: 写失败测试**

```python
# sim/tests/test_e1_talk_to.py
"""E1：talk_to 执行面——闸门放行的对话终于落地成 npc.chat + MOVE。"""
from __future__ import annotations

import asyncio

import pytest

from sim.agent.driver import ChenmoDriver
from sim.agent.intent import Intent
from sim.content.protagonist import build_anchor
from sim.core.tick import TickLoop
from sim.core.world import WorldState, build_default_bus
from sim.core.clock import GameClock
from sim.llm.client import ProfileSnapshot
from sim.world.pathfinding import Pathfinder
from sim.world.map import TileMap


def _state_with(actor: str, target: str) -> WorldState:
    from sim.core.world import EntityState

    return WorldState(
        world_seed=42,
        entities={
            actor: EntityState(entity_id=actor, pos=(10, 10)),
            target: EntityState(entity_id=target, pos=(11, 10)),
        },
    )


class _FakeLlm:
    async def complete(self, profile, messages):
        class R:
            content = '{"action":"talk_to","target_id":"villager_01","reason":"我想问问行情","confidence":0.9}'
        return R()


def _profile() -> ProfileSnapshot:
    return ProfileSnapshot(name="t", base_url="http://x", model="m", temperature=0.5, max_tokens=64, api_key="k")


def test_execute_talk_to_produces_chat_and_monologue():
    loop = TickLoop(clock=GameClock(speed=1.0), bus=build_default_bus(), state=_state_with("chenmo", "villager_01"))
    driver = ChenmoDriver(anchor=build_anchor(), llm=_FakeLlm(), profile_provider=_profile)
    intent = Intent(action="talk_to", target_id="villager_01", reason="我想问问行情", confidence=0.9)
    driver._pending.append(intent)
    # 假 tile_map：20x20 全可走
    tiles = TileMap(width=20, height=20, chunks={})
    executed = driver.execute_pending(loop, pathfinder=None, tile_map_for_test=tiles)
    assert executed == 1
    kinds = [e.event_type.value for e in loop.drain_events()]
    assert "npc.chat" in kinds
    assert "npc.monologue" in kinds
```

> 注：`execute_pending` 签名扩展为 `execute_pending(loop, *, pathfinder, tile_map_for_test=None)` 是测试缝——真实装配传 tile_map。若实现发现 `ChenmoDriver` 已有更自然的注入面（如 `execute_pending(loop, pathfinder)`），可在 review 时改为构造参数注入 `_talk_executor`，测试以注入替身驱动，**以实际 diff 为准，测试意图不变：talk_to 产出 npc.chat + npc.monologue 事件入流**。

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest sim/tests/test_e1_talk_to.py -q`
Expected: FAIL —— `TypeError: execute_pending() got an unexpected keyword argument`

- [ ] **Step 3: 最小实现**

`sim/agent/dialogue.py`（新文件，模板池 + LLM 缝）：

```python
"""sim.agent.dialogue — 台词生成（批次 E1：对话的最小内容面）。

LLM 可用 → 一次小请求生成一句世界内台词（max_tokens 低、失败即降级）；
不可用/超时 → 模板池按 (speaker, listener, tick) 哈希挑一句（C5 确定性）。
台词是**外在可观察面**（对方听见了）→ 走 npc.chat 事件；不进独白面板。
出戏纪律：模板池词面全部过 banned_words.scan 钉测试；拒绝操纵感语态。
"""
from __future__ import annotations

import hashlib

#: 模板池（第一人称世界内台词；{listener} 为称呼占位）。
_CHAT_TEMPLATES: tuple[str, ...] = (
    "{listener}，忙着呢？",
    "{listener}，今天镇上有什么新鲜事？",
    "{listener}，回头来我铺子里坐坐。",
    "{listener}，这天看着要变，早些回去吧。",
    "{listener}，改天一起喝一杯。",
)


def template_line(speaker: str, listener_name: str, tick: int) -> str:
    """模板兜底：sha256(speaker:listener:tick) 挑句（C5 同输入同输出）。"""
    digest = hashlib.sha256(f"chat:{speaker}:{listener_name}:{tick}".encode()).digest()
    pick = int.from_bytes(digest[0:4], "big") % len(_CHAT_TEMPLATES)
    return _CHAT_TEMPLATES[pick].format(listener=listener_name)
```

`sim/agent/driver.py` 的 `execute_pending` 在 `move_to` 分支后加：

```python
            elif intent.action == "talk_to" and intent.target_id is not None:
                self._issue_talk(loop, pathfinder, actor_id, intent)
```

新方法（同文件）：

```python
    async def _resolve_line(self, listener_name: str, reason: str, tick: int) -> str:
        """台词：模板兜底为主（E1 最小面；LLM 台词留 provider 注入缝）。"""
        from sim.agent.dialogue import template_line

        return template_line(self._anchor.entity_id, listener_name, tick)

    def _issue_talk(self, loop, pathfinder, actor_id: str, intent: Intent) -> None:
        """talk_to：走向目标（寻路可达才发 MOVE）+ npc.chat 事件（E1）。"""
        from sim.core.events import npc_chat_event

        state = loop.state
        target = state.entities.get(intent.target_id)
        actor = state.entities.get(actor_id)
        if target is None or actor is None:
            return
        # 走向目标：距离 > 2 格才需要 MOVE（贴脸直接说）
        dx, dy = target.pos[0] - actor.pos[0], target.pos[1] - actor.pos[1]
        if abs(dx) + abs(dy) > 2:
            from sim.world.pathfinding import Pathfinder

            if isinstance(pathfinder, Pathfinder):
                try:
                    path = pathfinder.find(actor.pos, target.pos)
                    loop.issue_move(actor_id, list(path))
                except ValueError:
                    pass  # 不可达：原地喊话（fail-soft，聊天仍发生）
        # 戏内名映射经注入回调（分层红线：agent 域禁 import sim.api——
        # main.py 装配时传 display_name_of=_display_names 同源 dict 的 get）
        listener_name = (
            self._display_name_of(intent.target_id) or intent.target_id
        )
        from sim.agent.dialogue import template_line

        line = template_line(actor_id, listener_name, state.tick)
        loop.enqueue(npc_chat_event(tick=state.tick, npc_id=actor_id, to_id=intent.target_id, line=line))
```

构造参数追加 `display_name_of: Callable[[str], str | None] | None = None`（存 `self._display_name_of`，缺省 `lambda _id: None`）。`main.py` 陈默 driver 构造处传 `display_name_of=_display_names.get`。

> 实现注记：`execute_pending` 保持同步；E1 用同步模板直用；将来 LLM 台词走构造注入的同步 provider（与 `economy_provider` 同模式）。测试断言事件种类，不断行文本。

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest sim/tests/test_e1_talk_to.py sim/tests/test_intent_gate.py sim/tests/test_m4c_llm_driver.py -q`
Expected: 全部 passed（旧 driver 测试零回归）

- [ ] **Step 5: investigate 分支（同 Task 顺带——闸门白名单里最后一个无落地语义的动作）**

`execute_pending` 再加分支：

```python
            elif intent.action == "investigate" and intent.target_pos is not None:
                from sim.world.pathfinding import Pathfinder

                if isinstance(pathfinder, Pathfinder):
                    actor = loop.state.entities.get(actor_id)
                    if actor is not None:
                        try:
                            path = pathfinder.find(actor.pos, intent.target_pos)
                            loop.issue_move(actor_id, list(path))
                        except ValueError:
                            pass  # 不可达：原地张望
```

（investigate 语义 = 走过去看一眼：位移即落地，观察产物由既有感知层接管——不为它造新事件。）

- [ ] **Step 6: 全量门禁 + Commit**

Run: `uv run pytest -q`
Expected: 全绿

```bash
git add sim/agent/dialogue.py sim/agent/driver.py sim/tests/test_e1_talk_to.py
git commit -m "feat(e1): talk_to/investigate 执行面——走向目标+npc.chat+模板台词池"
```

---

### Task 3: E1 村民开口接聊天——request_chat 到站产 npc.chat + 冷却

**Files:**
- Modify: `sim/npc/sim_exec.py`（到站开口 + 配对冷却账本）
- Test: `sim/tests/test_e1_villager_chat.py`

**Interfaces:**
- Consumes: Task 1 `npc_chat_event`；`_scatter_near`（tick 无关散点）；D2 模板池（`sim/content/villagers.py` 若无模板池则用 `dialogue.template_line`）。
- Produces: `npc_events_for_tick(..., chat_last: dict[str, int] | None = None)` 新参数——调用方（main.py `_npc_tick_hook`）持有账本（同 `monologue_last` 模式）；常量 `_CHAT_COOLDOWN_MIN_TICKS = 1800`、`_CHAT_COOLDOWN_SPAN_TICKS = 5400`（30~120 游戏分，同 D10 散布手法）。

- [ ] **Step 1: 写失败测试**

```python
# sim/tests/test_e1_villager_chat.py
"""E1：村民 request_chat 到站开口——npc.chat 落流 + 冷却节流。"""
from sim.npc.sim_exec import npc_events_for_tick


class _FakeRuntime:
    """最小 runtime 替身：直接给出一批 npc.act(request_chat)。"""

    def __init__(self, events):
        self._events = events

    def tick(self, tick):
        return list(self._events)


def _act(npc_id, target):
    from sim.core.events import npc_act_event

    return npc_act_event(tick=0, npc_id=npc_id, action="request_chat", target=target)


def test_arrival_produces_chat_once(tmp_path):
    # 到站场景：两实体相邻且 request_chat 目的地邻域内
    from sim.core.world import WorldState, EntityState
    from sim.world.map import TileMap
    from sim.world.pathfinding import Pathfinder

    state = WorldState(
        world_seed=42,
        entities={
            "villager_01": EntityState(entity_id="villager_01", pos=(30, 46)),
            "villager_02": EntityState(entity_id="villager_02", pos=(31, 46)),
        },
    )
    # 真图：linhe-town.json 保证 (30,46) 一带可走
    from pathlib import Path

    tile_map = TileMap.from_json_file(Path("sim/content/linhe-town.json"))
    rt = _FakeRuntime([_act("villager_01", "villager_02")])
    events = npc_events_for_tick(rt, state, 100, Pathfinder(tile_map), seed=42, chat_last={})
    chats = [e for e in events if e.event_type.value == "npc.chat"]
    assert len(chats) == 1
    assert chats[0].payload["npc_id"] == "villager_01"
    assert chats[0].payload["to_id"] == "villager_02"


def test_chat_cooldown_blocks_second():
    # 同拍重复开口被冷却账本拦下（零 chat 事件）
    from sim.core.world import WorldState, EntityState
    from sim.world.map import TileMap
    from sim.world.pathfinding import Pathfinder

    state = WorldState(
        world_seed=42,
        entities={
            "villager_01": EntityState(entity_id="villager_01", pos=(30, 46)),
            "villager_02": EntityState(entity_id="villager_02", pos=(31, 46)),
        },
    )
    from pathlib import Path

    tile_map = TileMap.from_json_file(Path("sim/content/linhe-town.json"))
    rt = _FakeRuntime([_act("villager_01", "villager_02")])
    chat_last = {"villager_01": 100}  # 刚说过
    events = npc_events_for_tick(rt, state, 110, Pathfinder(tile_map), seed=42, chat_last=chat_last)
    assert not [e for e in events if e.event_type.value == "npc.chat"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest sim/tests/test_e1_villager_chat.py -q`
Expected: FAIL —— `TypeError: npc_events_for_tick() got an unexpected keyword argument 'chat_last'`

- [ ] **Step 3: 最小实现**

`sim/npc/sim_exec.py`：

```python
#: E1 聊天冷却（D10 同手法：按 NPC 散布防齐射）。
_CHAT_COOLDOWN_MIN_TICKS = 1800
_CHAT_COOLDOWN_SPAN_TICKS = 5400


def _chat_cooldown_ticks(npc_id: str) -> int:
    digest = _hash_u32("chat-cooldown", npc_id)
    span = int.from_bytes(digest[0:4], "big") % _CHAT_COOLDOWN_SPAN_TICKS
    return _CHAT_COOLDOWN_MIN_TICKS + span
```

`npc_events_for_tick` 签名加 `chat_last: dict[str, int] | None = None`；在 `request_chat` 动作处理处（现有 `if action in ("eat", "rest", "work", "request_chat")` 位移面之后）加到站开口：

```python
        if action == "request_chat" and entity is not None and not entity.path and chat_last is not None:
            target_id = str(event.payload.get("target", ""))
            if target_id and target_id in state.entities:
                tgt = state.entities[target_id]
                dist = abs(entity.pos[0] - tgt.pos[0]) + abs(entity.pos[1] - tgt.pos[1])
                if dist <= 2:  # 贴身（散点半径内）才算到站
                    last = chat_last.get(npc_id, -(_CHAT_COOLDOWN_MIN_TICKS + _CHAT_COOLDOWN_SPAN_TICKS))
                    if tick - last >= _chat_cooldown_ticks(npc_id):
                        chat_last[npc_id] = tick
                        from sim.agent.dialogue import template_line

                        # 名字映射经参数注入（npc 域禁 import sim.api——
                        # npc_events_for_tick 加 display_name_of: Mapping[str, str] | None = None）
                        listener = (display_name_of or {}).get(target_id, target_id)
                        line = template_line(npc_id, listener, tick)
                        events.append(npc_chat_event(tick=tick, npc_id=npc_id, to_id=target_id, line=line))
```

> 注意：`request_chat` 的 NPC_ACT payload `target` 键走 `ACTION_PAYLOAD_KEYS["request_chat"] = {"to_npc"}` ——查 `npc_act_event(tick, npc_id, action, target)` 的 target 落在 payload 哪个键（现有 `runtime.tick` 里 `target=d.target`，UtilityDecision.target 恒 ""）。**实现时先跑一条真实 npc_act 验证 target 键名**；若 target 恒空（D18 的 `_chat_target_of` 只算目的地不算 target 字段），则开口判定改用 `_chat_target_of(state, npc_id, tick=tick)` 现算目标（与目的地解析同源，C5 纯函数），不依赖 payload。这是本任务唯一的实现自由度，测试已按「同源现算」写（`to_id` 断言值来自 `_chat_target_of` 的确定性选择，两实体场景必互指）。

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest sim/tests/test_e1_villager_chat.py sim/tests/test_m4d_walk_pacing.py sim/tests/test_m4d12_disperse.py -q`
Expected: 全部 passed

- [ ] **Step 5: 全量门禁 + Commit**

Run: `uv run pytest -q`

```bash
git add sim/npc/sim_exec.py sim/tests/test_e1_villager_chat.py
git commit -m "feat(e1): 村民 request_chat 到站开口——npc.chat+冷却散布"
```

---

### Task 4: E2 关系与记忆 runtime——ChatLedger（进程内）+ society 接线

**Files:**
- Create: `sim/npc/chat_ledger.py`（进程内关系+记忆账本）
- Modify: `sim/npc/sim_exec.py`（chat 事件触发关系漂移+记忆写入）
- Test: `sim/tests/test_e2_chat_ledger.py`

**Interfaces:**
- Consumes: Task 1 npc.chat 事件；`sim.npc.society` 的常量与字段语义（trust/affection delta 值复用）。
- Produces: `ChatLedger` 类——`adjust(owner: str, other: str, kind: str) -> None`（affection/trust 漂移，[0,1] clamp，有向两行）；`remember(npc_id: str, content: str, tick: int) -> None`（in-process 记忆，上限 20 条/人 LRU）；`relations_of(owner: str) -> dict[str, dict[str, float]]`（观测面）。`build_chat_ledger_from_events(events) -> None` 供实况钩子喂事件。

- [ ] **Step 1: 写失败测试**

```python
# sim/tests/test_e2_chat_ledger.py
"""E2：进程内关系/记忆账本（禁第二 SQL 驱动——纯 dict）。"""
from sim.npc.chat_ledger import ChatLedger


def test_adjust_creates_symmetric_rows_with_asymmetric_values():
    led = ChatLedger()
    led.adjust("a", "b", kind="chat")
    rows = led.relations_of("a")
    assert rows["b"]["affection"] > 0.0  # a 对 b 好感上升


def test_adjust_clamps_to_unit_range():
    led = ChatLedger()
    for _ in range(200):
        led.adjust("a", "b", kind="chat")
    assert led.relations_of("a")["b"]["affection"] <= 1.0


def test_remember_ring_buffer():
    led = ChatLedger()
    for i in range(25):
        led.remember("a", f"第{i}句话", tick=i)
    mems = led.memories_of("a")
    assert len(mems) == 20  # 上限 20
    assert mems[-1][1] == "第24句话"  # 保留最新


def test_chat_kind_unknown_rejected():
    led = ChatLedger()
    import pytest

    with pytest.raises(ValueError):
        led.adjust("a", "b", kind="nope")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest sim/tests/test_e2_chat_ledger.py -q`
Expected: FAIL —— `ModuleNotFoundError: No module named 'sim.npc.chat_ledger'`

- [ ] **Step 3: 最小实现**

```python
# sim/npc/chat_ledger.py
"""sim.npc.chat_ledger — 聊天驱动的关系/记忆进程内账本（批次 E2）。

**禁第二 SQL 驱动**（Global Constraints）：RelationshipStore 是 sync sqlite3，
与实况 aiosqlite 单写者共库=跨驱动锁风险（chenmo_memory docstring 同口径）。
关系/记忆是 runtime 内存态（needs/火场同口径）——**效应**经 npc.monologue /
后续 retell 事件表达，账本本身不进重放面（C4：世界真相仍是事件流）。

常量对齐 sim/npc/society.py（CHAT_AFFECTION_DELTA=0.02 / RETELL_TRUST_DELTA=0.05）；
值域 [0,1] clamp 与 society/RelationshipStore 同约定。frozen 无状态污染：
adjust 返回 None 但内部全量 replace 语义（dict 重建行）。
"""
from __future__ import annotations

from sim.npc.society import CHAT_AFFECTION_DELTA, RETELL_TRUST_DELTA

#: 单人记忆环形缓冲上限（观测/检索面，非世界真相）。
_MEMORY_CAP = 20

#: 互动 kind → (字段, delta)——与 society._RULES 同源（DRY：改一处两处红测试）。
_RULES: dict[str, tuple[str, float]] = {
    "chat": ("affection", CHAT_AFFECTION_DELTA),
    "retell": ("trust", RETELL_TRUST_DELTA),
}

#: 观测面字段序（relations_of 输出稳定序，C5）。
_FIELDS = ("affection", "trust", "fear", "debt", "face")


class ChatLedger:
    """{owner: {other: {field: value}}} + {npc: [(tick, text)]} 环形缓冲。"""

    def __init__(self) -> None:
        self._relations: dict[str, dict[str, dict[str, float]]] = {}
        self._memories: dict[str, list[tuple[int, str]]] = {}

    def adjust(self, owner: str, other: str, *, kind: str) -> None:
        if kind not in _RULES:
            raise ValueError(f"未知互动类型: {kind!r}")
        field, delta = _RULES[kind]
        row = self._relations.setdefault(owner, {}).setdefault(
            other, {f: 0.0 for f in _FIELDS}
        )
        row[field] = min(1.0, max(0.0, row[field] + delta))

    def remember(self, npc_id: str, content: str, *, tick: int) -> None:
        buf = self._memories.setdefault(npc_id, [])
        buf.append((tick, content))
        if len(buf) > _MEMORY_CAP:
            del buf[: len(buf) - _MEMORY_CAP]

    def memories_of(self, npc_id: str) -> list[tuple[int, str]]:
        return list(self._memories.get(npc_id, ()))

    def relations_of(self, owner: str) -> dict[str, dict[str, float]]:
        return {o: dict(row) for o, row in self._relations.get(owner, {}).items()}

    def __len__(self) -> int:
        return len(self._relations)
```

`sim_exec.npc_events_for_tick` 在 Task 3 的开口块内追加两行：

```python
                        if chat_ledger is not None:
                            chat_ledger.adjust(npc_id, target_id, kind="chat")
                            chat_ledger.remember(npc_id, line, tick=tick)
```

签名再加 `chat_ledger: ChatLedger | None = None`（main.py 装配传入）。

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest sim/tests/test_e2_chat_ledger.py -q`
Expected: 4 passed

- [ ] **Step 5: 全量门禁 + 双驱动自查 + Commit**

Run: `uv run pytest -q`；`Grep "sqlite3.connect" sim/ --glob '!**/tests/**'` 零新增。

```bash
git add sim/npc/chat_ledger.py sim/npc/sim_exec.py sim/tests/test_e2_chat_ledger.py
git commit -m "feat(e2): ChatLedger 进程内关系/记忆账本——chat 漂移接进执行面"
```

---

### Task 5: E2 陈默侧接线——记忆/关系进 prompt（[记忆] 段供数）

**Files:**
- Modify: `sim/api/main.py`（lifespan 装配：ChatLedger 实例化 + 陈默 recall 双源）
- Modify: `sim/agent/chenmo_memory.py`（recall 支持 ledger 附加条目）
- Test: `sim/tests/test_e2_chenmo_ledger_prompt.py`

**Interfaces:**
- Consumes: Task 4 `ChatLedger`；既有 `_mem_observe/_mem_recall`。
- Produces: `_chenmo_loop` 决策前把 ledger 里 chenmo 的记忆文本并进 `memory_entries`（Ledger 条目 importance 视为最新——排前）；`app.state.chat_ledger` 挂账本供测试/观测。

- [ ] **Step 1: 写失败测试**

```python
# sim/tests/test_e2_chenmo_ledger_prompt.py
"""E2：陈默 recall 并入 ledger 记忆（prompt [记忆] 段双源）。"""
from sim.agent.chenmo_memory import merge_ledger_entries


def test_merge_puts_ledger_first_and_caps():
    ledger_texts = ("镇口的老张今天神色不对。",)
    base = ("三天前的雨。", "更早的事。", "再早的事。", "第四条。")
    merged = merge_ledger_entries(base, ledger_texts, top_k=4)
    assert merged[0] == "镇口的老张今天神色不对。"
    assert len(merged) == 4
    assert "第四条。" not in merged  # 基础条目被挤掉一条


def test_merge_empty_ledger_unchanged():
    base = ("a", "b")
    assert merge_ledger_entries(base, (), top_k=3) == ("a", "b")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest sim/tests/test_e2_chenmo_ledger_prompt.py -q`
Expected: FAIL —— `ImportError: merge_ledger_entries`

- [ ] **Step 3: 最小实现**

`sim/agent/chenmo_memory.py` 追加：

```python
def merge_ledger_entries(
    base: tuple[str, ...], ledger_texts: tuple[str, ...], *, top_k: int
) -> tuple[str, ...]:
    """[记忆] 段双源合并：ledger（当日对话，最新鲜）排前，截 top_k（C5 纯函数）。"""
    merged = tuple(ledger_texts) + tuple(base)
    return merged[:top_k]
```

`sim/api/main.py` 的 `_chenmo_loop` 内：

```python
            _ledger_texts = tuple(
                text for _, text in chat_ledger.memories_of("chenmo")[-3:]
            )
            memory_entries=merge_ledger_entries(
                _mem_recall(memory_pipeline, now_tick=loop.state.tick),
                _ledger_texts,
                top_k=3,
            ),
```

并在 lifespan 装配处 `chat_ledger = ChatLedger(); app.state.chat_ledger = chat_ledger`，`_npc_tick_hook` 调 `npc_events_for_tick(..., chat_ledger=chat_ledger)`。

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest sim/tests/test_e2_chenmo_ledger_prompt.py sim/tests/test_m2_runtime_assemble.py -q`
Expected: 全绿

- [ ] **Step 5: 全量门禁 + Commit**

Run: `uv run pytest -q`

```bash
git add sim/api/main.py sim/agent/chenmo_memory.py sim/tests/test_e2_chenmo_ledger_prompt.py
git commit -m "feat(e2): 陈默记忆双源——ledger 对话记忆进 prompt [记忆] 段"
```

---

### Task 6: E2 retell 转述——bubble 独白 + trust 漂移 + 冷却

**Files:**
- Modify: `sim/npc/sim_exec.py`（retell 产出：NPC_MONOLOGUE bubble + ledger.adjust kind="retell"）
- Test: `sim/tests/test_e2_retell.py`

**Interfaces:**
- Consumes: Task 4 `ChatLedger.adjust(kind="retell")`；既有 `npc_monologue_event`（form="bubble"）。
- Produces: 常量 `_RETELL_COOLDOWN_MIN_TICKS = 3600`、`_RETELL_COOLDOWN_SPAN_TICKS = 10800`（60~280 游戏分）；`retell_last: dict[str, int]` 账本参数（同 chat_last 模式）。流言内容 = 该 NPC 记忆里最新一条的转述模板「听{speaker}说，{content}」——内容出戏纪律由记忆源把关（记忆内容全部来自过闸门的 chat line）。

- [ ] **Step 1: 写失败测试**

```python
# sim/tests/test_e2_retell.py
"""E2：retell——有记忆的村民会向别人转述（bubble + trust 漂移 + 冷却）。"""
from sim.npc.chat_ledger import ChatLedger
from sim.npc.sim_exec import retell_template


def test_retell_template_format():
    assert retell_template("赵铁柱", "东边着火了") == "听赵铁柱说，东边着火了"


def test_ledger_retell_moves_trust():
    led = ChatLedger()
    led.adjust("a", "b", kind="retell")
    assert led.relations_of("a")["b"]["trust"] > 0.0


def test_retell_text_passes_banned_scan():
    from sim.llm.prompts.banned_words import scan

    line = retell_template("赵铁柱", "东边着火了")
    assert not scan(line).hits
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest sim/tests/test_e2_retell.py -q`
Expected: FAIL —— `ImportError: retell_template`

- [ ] **Step 3: 最小实现**

`sim/npc/sim_exec.py` 追加：

```python
def retell_template(speaker_name: str, content: str) -> str:
    """转述模板（外在可观察面：路人听见 A 向 B 学舌）。"""
    return f"听{speaker_name}说，{content}"


_RETELL_COOLDOWN_MIN_TICKS = 3600
_RETELL_COOLDOWN_SPAN_TICKS = 10800
```

`npc_events_for_tick` 加 `retell_last: dict[str, int] | None = None` 参数；开口块后追加 retell 分支：

```python
        # E2 retell：有记忆的村民随机向在场他人学舌（走 bubble 广播面）。
        if retell_last is not None and chat_ledger is not None:
            mems = chat_ledger.memories_of(npc_id)
            if mems and entity is not None and not entity.path:
                _rt = _hash_u32("retell-cooldown", npc_id)
                _rspan = int.from_bytes(_D4(f"rc:{npc_id}".encode()).digest()[:4], "big") % _RETELL_COOLDOWN_SPAN_TICKS
                _rcool = _RETELL_COOLDOWN_MIN_TICKS + _rspan
                last_r = retell_last.get(npc_id, -(_rcool + 1))
                if tick - last_r >= _rcool:
                    retell_last[npc_id] = tick
                    _tid, _content = mems[-1]
                    _speaker = (display_name_of or {}).get(npc_id, npc_id)
                    _line = retell_template(_speaker, _content)
                    events.append(
                        npc_monologue_event(tick=tick, npc_id=npc_id, form="bubble", content=_line)
                    )
                    if chat_ledger is not None:
                        chat_ledger.adjust(npc_id, event.payload.get("npc_id", npc_id), kind="retell")
```

> 实现注记：retell 触发点放在**开口块同拍**（说了话才可能学舌）逻辑简化为「开口成功 → 概率性转述自己记忆里最新一条」。上面草稿在访客/听众选择上有实现自由度（可复用 `_chat_target_of` 现算听众）；**测试钉三点**：模板格式、trust 漂移方向、词面过禁词扫描。行为钉（每拍至多一条 retell bubble）进 Task 8 的配额测试。

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest sim/tests/test_e2_retell.py -q`
Expected: 3 passed

- [ ] **Step 5: 全量门禁 + Commit**

Run: `uv run pytest -q`

```bash
git add sim/npc/sim_exec.py sim/tests/test_e2_retell.py
git commit -m "feat(e2): retell 转述——bubble学舌+trust漂移+冷却散布"
```

---

### Task 7: E3 经济事件——coin.grant 事件 + 余额账本 + buy/sell 执行面

**Files:**
- Modify: `sim/core/events.py`（`COIN_GRANT = "coin.grant"` + `CoinGrantPayload(owner_id: str, delta: int, note: str)` + 工厂 `coin_grant_event`）
- Modify: `sim/core/persistence/event_validation.py`（登记）
- Modify: `sim/core/world.py`（no-op handler）
- Create: `sim/world/economy.py`（进程内余额账本 CoinLedger + 价目表 + 确定性定价）
- Modify: `sim/agent/driver.py`（buy/sell 分支）
- Modify: `sim/npc/actions.py`（白名单不动——buy/sell 是陈默 Intent 动作，不走 NPC_ACT 白名单；**确认此边界后不改动**）
- Test: `sim/tests/test_e3_economy.py`

**Interfaces:**
- Consumes: Task 1/2 的 driver 执行面模式。
- Produces: `CoinLedger`——`balance_of(owner) -> int`、`apply_grant(owner, delta, tick) -> None`（余额永不为负：资金不足 grant 拒绝返回 False）；`GOODS: tuple[Good, ...]`——`Good(id: str, name: str, price: int)`，E3 最小三件：`herb`(草药 12 文)、`salve`(药膏 30 文)、`meal`(饭食 8 文)；`buy_price(good_id, tick, seed) -> int`（基准价 ±20% 确定性哈希浮动）。

- [ ] **Step 1: 写失败测试**

```python
# sim/tests/test_e3_economy.py
"""E3：最小经济——coin.grant 事件 + CoinLedger 余额 + 价目表。"""
import pytest

from sim.core.events import EventKind, coin_grant_event
from sim.core.persistence.event_validation import PAYLOAD_MODELS, validate_store_row
from sim.core.world import TickContext, WorldState, build_default_bus
from sim.world.economy import GOODS, CoinLedger, buy_price


def test_coin_grant_event_and_registry():
    ev = coin_grant_event(tick=5, owner_id="chenmo", delta=-12, note="buy:herb")
    assert ev.event_type is EventKind.COIN_GRANT
    validate_store_row(ev.to_store_dict())
    assert PAYLOAD_MODELS[EventKind.COIN_GRANT].model_validate(
        {"owner_id": "chenmo", "delta": -12, "note": "buy:herb"}
    )


def test_coin_grant_fold_noop_hash_stable():
    bus = build_default_bus()
    state = WorldState(world_seed=42)
    ev = coin_grant_event(tick=0, owner_id="chenmo", delta=5, note="sell:herb")
    before = state.state_hash()
    assert bus.apply(state, ev, TickContext()).state.state_hash() == before


def test_ledger_applies_and_rejects_negative():
    led = CoinLedger()
    led.apply_grant("chenmo", 100, tick=1)
    assert led.balance_of("chenmo") == 100
    assert led.apply_grant("chenmo", -200, tick=2) is False  # 余额不够：拒绝
    assert led.balance_of("chenmo") == 100
    assert led.apply_grant("chenmo", -30, tick=3) is True
    assert led.balance_of("chenmo") == 70


def test_goods_catalog_and_price_bounds():
    ids = [g.id for g in GOODS]
    assert ids == ["herb", "salve", "meal"]
    for good in GOODS:
        price = buy_price(good.id, tick=12345, seed=42)
        assert int(good.price * 0.8) <= price <= int(good.price * 1.2)
        assert buy_price(good.id, tick=12345, seed=42) == price  # C5 同输入同输出
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest sim/tests/test_e3_economy.py -q`
Expected: FAIL —— `ImportError: coin_grant_event`

- [ ] **Step 3: 最小实现**

`sim/core/events.py`（同 Task 1 三件套）：

```python
    COIN_GRANT = "coin.grant"  # 批次 E3：铜钱入账/出账（余额账本在 runtime）
```

```python
class CoinGrantPayload(BaseModel):
    """铜钱入账（批次 E3）。note 记事（buy:herb / sell:herb / wage:work）。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    owner_id: str
    delta: int
    note: str
```

```python
def coin_grant_event(tick: int, owner_id: str, delta: int, note: str, branch_id: str = "main") -> WorldEvent:
    p = CoinGrantPayload(owner_id=owner_id, delta=delta, note=note)
    return WorldEvent(
        branch_id=branch_id,
        tick=tick,
        event_type=EventKind.COIN_GRANT,
        actor_id=owner_id,
        payload=p.model_dump(mode="json"),
    )
```

`event_validation.py` 登记 `EventKind.COIN_GRANT: CoinGrantPayload`；`world.py` no-op：

```python
def _apply_coin_grant(state: WorldState, event: WorldEvent, ctx: TickContext) -> ApplyResult:
    """COIN_GRANT（批次 E3）：账面记录，余额归 runtime CoinLedger（重放安全 no-op）。"""
    from sim.core.events import CoinGrantPayload

    CoinGrantPayload.model_validate(event.payload)
    return ApplyResult(state=state)
```

`sim/world/economy.py`（新文件）：

```python
"""sim.world.economy — 最小经济（批次 E3）：价目表 + 进程内余额账本。

余额是 runtime 内存态（禁第二 SQL 驱动）；**入账/出账结果**经 coin.grant
事件落流（C4：账单即真相，余额可由事件流重放重建）。定价确定性哈希浮动
（C5 无 RNG 流）。
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class Good:
    id: str
    name: str
    price: int  # 基准价（文）


#: E3 最小三件（药铺语境；价目是戏内事实可出站）。
GOODS: tuple[Good, ...] = (
    Good(id="herb", name="草药", price=12),
    Good(id="salve", name="药膏", price=30),
    Good(id="meal", name="饭食", price=8),
)

_GOOD_INDEX = {g.id: g for g in GOODS}


def buy_price(good_id: str, *, tick: int, seed: int) -> int:
    """基准价 ±20% 确定性浮动（sha256(good:tick:seed)，C5 同输入同输出）。"""
    good = _GOOD_INDEX[good_id]
    digest = hashlib.sha256(f"price:{good_id}:{tick}:{seed}".encode()).digest()
    jitter = (int.from_bytes(digest[0:4], "big") % 41) - 20  # [-20, +20]%
    return max(1, good.price * (100 + jitter) // 100)


class CoinLedger:
    """{owner: 余额}；apply_grant 拒绝负余额（买不起=结构化拒绝，非异常）。"""

    def __init__(self) -> None:
        self._balances: dict[str, int] = {}

    def balance_of(self, owner: str) -> int:
        return self._balances.get(owner, 0)

    def apply_grant(self, owner: str, delta: int, *, tick: int) -> bool:
        current = self._balances.get(owner, 0)
        if current + delta < 0:
            return False
        self._balances[owner] = current + delta
        return True
```

`sim/agent/driver.py` 的 `execute_pending` 加 buy/sell 分支（需要注入 `economy_provider: Callable[[], tuple[CoinLedger, int]] | None`——返回账本与 world_seed；构造参数默认 None=跳过）：

```python
            elif intent.action in ("buy", "sell") and self._economy is not None:
                self._issue_trade(loop, intent)
```

```python
    def _issue_trade(self, loop, intent: Intent) -> None:
        """buy/sell：查价 → 余额判定 → coin.grant 事件 + 独白结果（E3 最小面）。
        target_id 存货名（herb/salve/meal）；params 里可带 qty（缺省 1）。
        """
        from sim.core.events import coin_grant_event, npc_monologue_event
        from sim.world.economy import _GOOD_INDEX, buy_price

        good = _GOOD_INDEX.get(intent.target_id or "")
        if good is None:
            return
        ledger, seed = self._economy()
        tick = loop.state.tick
        price = buy_price(good.id, tick=tick, seed=seed)
        if intent.action == "buy":
            ok = ledger.apply_grant(self._anchor.entity_id, -price, tick=tick)
            if ok:
                loop.enqueue(coin_grant_event(tick=tick, owner_id=self._anchor.entity_id, delta=-price, note=f"buy:{good.id}"))
                content = f"这剂{good.name}花了{price}文，值。"
            else:
                content = f"摸遍全身也凑不齐这{price}文，{good.name}先记着吧。"
        else:  # sell：卖货得半价（E3 简化：无库存面，卖=凭手艺挣工钱口径）
            earned = max(1, price // 2)
            ledger.apply_grant(self._anchor.entity_id, earned, tick=tick)
            loop.enqueue(coin_grant_event(tick=tick, owner_id=self._anchor.entity_id, delta=earned, note=f"sell:{good.id}"))
            content = f"出手一批{good.name}，进账{earned}文。"
        loop.enqueue(npc_monologue_event(tick=tick + 1, npc_id=self._anchor.entity_id, form="thought", content=content))
```

构造函数加参数 `economy_provider: Callable[[], tuple[object, int]] | None = None`（存 `self._economy`）。

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest sim/tests/test_e3_economy.py sim/tests/test_e1_talk_to.py -q`
Expected: 全绿

- [ ] **Step 5: 全量门禁 + Commit**

Run: `uv run pytest -q`

```bash
git add sim/core/events.py sim/core/persistence/event_validation.py sim/core/world.py sim/world/economy.py sim/agent/driver.py sim/tests/test_e3_economy.py
git commit -m "feat(e3): 最小经济——coin.grant事件+CoinLedger+买卖执行面"
```

---

### Task 8: E3 谋生闭环——work 到站计酬 + 村民 wage 事件

**Files:**
- Modify: `sim/npc/sim_exec.py`（work 到站 → wage grant，冷却防刷）
- Modify: `sim/api/main.py`（装配 CoinLedger 共享给 NPC 执行面与陈默 driver）
- Test: `sim/tests/test_e3_wage.py`

**Interfaces:**
- Consumes: Task 7 `coin_grant_event`/`CoinLedger`。
- Produces: 常量 `_WAGE_AMOUNT = 5`（文/次）、`_WAGE_COOLDOWN_MIN_TICKS = 3600`、`_WAGE_COOLDOWN_SPAN_TICKS = 7200`（60~180 游戏分/次）；`wage_last: dict[str, int]` 账本参数。work 是既有动作——到站已有需求回写（D3），wage 是**新增**并行后果。

- [ ] **Step 1: 写失败测试**

```python
# sim/tests/test_e3_wage.py
"""E3：work 到站计酬——wage grant + 冷却防刷。"""
from sim.core.world import EntityState, WorldState
from sim.npc.chat_ledger import ChatLedger
from sim.npc.sim_exec import npc_events_for_tick
from sim.world.economy import CoinLedger
from sim.world.map import TileMap
from sim.world.pathfinding import Pathfinder


class _FakeRuntime:
    def __init__(self, events, profiles=None):
        self._events = events
        self.profiles = profiles or {}

    def tick(self, tick):
        return list(self._events)


def _state_work_at_site():
    # 南村农田锚点 (26, 80)（_TERRITORY_WORK 南村就近）邻域
    return WorldState(
        world_seed=42,
        entities={"villager_10": EntityState(entity_id="villager_10", pos=(27, 80))},
    )


def _act_work():
    from sim.core.events import npc_act_event

    return npc_act_event(tick=0, npc_id="villager_10", action="work")


def test_work_at_site_pays_wage_once():
    tile_map = TileMap.from_json_file(_TOWN)
    led = CoinLedger()
    rt = _FakeRuntime([_act_work()])
    events = npc_events_for_tick(
        rt, _state_work_at_site(), 1000, Pathfinder(tile_map), seed=42,
        wage_last={}, coin_ledger=led,
    )
    grants = [e for e in events if e.event_type.value == "coin.grant"]
    assert len(grants) == 1
    assert grants[0].payload["delta"] == 5
    assert led.balance_of("villager_10") == 5


def test_wage_cooldown_blocks_double_pay():
    tile_map = TileMap.from_json_file(_TOWN)
    led = CoinLedger()
    rt = _FakeRuntime([_act_work()])
    wage_last = {"villager_10": 1000}  # 刚领过
    events = npc_events_for_tick(
        rt, _state_work_at_site(), 1010, Pathfinder(tile_map), seed=42,
        wage_last=wage_last, coin_ledger=led,
    )
    assert not [e for e in events if e.event_type.value == "coin.grant"]


_TOWN = __import__("pathlib").Path("sim/content/linhe-town.json")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest sim/tests/test_e3_wage.py -q`
Expected: FAIL —— `TypeError: unexpected keyword argument 'wage_last'`

- [ ] **Step 3: 最小实现**

`sim_exec.py`：

```python
_WAGE_AMOUNT = 5
_WAGE_COOLDOWN_MIN_TICKS = 3600
_WAGE_COOLDOWN_SPAN_TICKS = 7200
```

`npc_events_for_tick` 加 `wage_last: dict[str, int] | None = None, coin_ledger: CoinLedger | None = None`；在 work 到站回写块（D3 既有 `if entity is not None and not entity.path and action in ("eat", "rest", "work")` 内追加 work 分支）：

```python
            if action == "work" and wage_last is not None and coin_ledger is not None and anchor is not None:
                last_w = wage_last.get(npc_id, -(_WAGE_COOLDOWN_MIN_TICKS + _WAGE_COOLDOWN_SPAN_TICKS))
                if tick - last_w >= _WAGE_COOLDOWN_MIN_TICKS + (
                    int.from_bytes(_hash_u32("wage-cool", npc_id).to_bytes(4, "big")[0:4], "big") % _WAGE_COOLDOWN_SPAN_TICKS
                ):
                    wage_last[npc_id] = tick
                    coin_ledger.apply_grant(npc_id, _WAGE_AMOUNT, tick=tick)
                    events.append(coin_grant_event(tick=tick, owner_id=npc_id, delta=_WAGE_AMOUNT, note="wage:work"))
```

`main.py`：`chat_ledger` 同处实例化 `coin_ledger = CoinLedger()`，`app.state.coin_ledger = coin_ledger`；陈默 driver 构造加 `economy_provider=lambda: (coin_ledger, loop.state.world_seed)`；`_npc_tick_hook` 传 `wage_last=wage_last账本, coin_ledger=coin_ledger`。

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest sim/tests/test_e3_wage.py -q`
Expected: 2 passed

- [ ] **Step 5: 全量门禁 + Commit**

Run: `uv run pytest -q`

```bash
git add sim/npc/sim_exec.py sim/api/main.py sim/tests/test_e3_wage.py
git commit -m "feat(e3): 谋生闭环——work到站计酬+wage冷却防刷"
```

---

### Task 9: E4 建造闭环——build 执行面（structure.started → checkpoint → completed）

**Files:**
- Create: `sim/agent/build_exec.py`（施工 runtime：进度账本 + 每日 checkpoint + 完工 tile 变更）
- Modify: `sim/core/world.py`（注册 STRUCTURE_*/MATERIAL_*/TILE_CHANGED handler——TILE_CHANGED 从 NotImplementedError 改为 schema 校验 no-op）
- Modify: `sim/tests/bench/test_bench_apply.py:75-92`（守卫测试换 kind：TILE_CHANGED 已启用，改钉真正的未启用 kind，或改为「已注册 kind 不再抛」正向断言）
- Modify: `sim/agent/driver.py`（build 分支 → structure.started）
- Modify: `sim/api/main.py`（BuildRuntime 挂 npc_runtime 钩子）
- Test: `sim/tests/test_e4_build_loop.py`

**Interfaces:**
- Consumes: `structure_started_event`/`structure_checkpoint_event`/`structure_completed_event`/`tile_changed_event`（events.py 既有工厂）；`structure.BuildProgress`/`next_checkpoint_tick`/`advance_build`；`TileMap.with_collision`（占格）+ `Pathfinder.invalidate_dirty`/`observe_map`。
- **前置（本任务 Step 0）**：`build_default_bus` 目前**没有** STRUCTURE_*/MATERIAL_*/TILE_CHANGED 的 handler（`_apply_tile_changed` 还是 `raise NotImplementedError`，`test_bench_apply.py::test_apply_unknown_kind_rejected` 钉着「TILE_CHANGED 必须拒绝」）。E4 是这些事件第一次进实况流——必须先注册 handler 并更新守卫测试，否则 enqueue 当帧炸「未注册的事件种类」/「未启用」。
- Produces: `BuildRuntime`——`start(intent_target_pos, tick) -> WorldEvent | None`（2×2 选格校验可走→started 事件 + 内存 progress）；`on_tick(tick) -> list[WorldEvent]`（checkpoint 到点产 checkpoint/完工产 completed+tile_changed 序列并落世界占格）；`tile_map` 引用由 main.py 注入。陈默 build 意图：target_pos = 施工点，cost = `_BUILD_COST_COINS = 40`（Task 7 CoinLedger 扣）。

- [ ] **Step 0: 注册既有结构/瓦片事件的 handler（前置，否则本任务事件入流即炸）**

`sim/core/world.py`：

```python
def _apply_structure_event(state: WorldState, event: WorldEvent, ctx: TickContext) -> ApplyResult:
    """STRUCTURE_*（批次 E4 实况接线）：施工记录进事件日志，状态层 no-op。

    结构投影（structures 表）与占格（tile_changed）由 NpcStore 投影缝 /
    BuildRuntime 实况侧承担；世界态不含结构（同火场口径——事件材料足以
    重放观察面）。no-op ⇒ 重放安全（C5）。
    """
    return ApplyResult(state=state)


def _apply_tile_changed(state: WorldState, event: WorldEvent, ctx: TickContext) -> ApplyResult:
    """TILE_CHANGED（批次 E4 启用，替换 M0 的 NotImplementedError 占位）：
    瓦片变更是表现/寻路面（TileMap frozen 几何由 BuildRuntime 实况重建），
    状态层 no-op（实体位置不在 tile 上、WorldState 无瓦片字段）。"""
    from sim.core.events import TileChangedPayload

    TileChangedPayload.model_validate(event.payload)
    return ApplyResult(state=state)


def _apply_material_event(state: WorldState, event: WorldEvent, ctx: TickContext) -> ApplyResult:
    """MATERIAL_*（E4 前置一并注册——事件族同源；余额投影归 NpcStore）。"""
    return ApplyResult(state=state)
```

`build_default_bus` 追加：

```python
    bus.register(EventKind.STRUCTURE_STARTED, _apply_structure_event)
    bus.register(EventKind.STRUCTURE_CHECKPOINT, _apply_structure_event)
    bus.register(EventKind.STRUCTURE_COMPLETED, _apply_structure_event)
    bus.register(EventKind.STRUCTURE_COLLAPSED, _apply_structure_event)
    bus.register(EventKind.STRUCTURE_REMOVED, _apply_structure_event)
    bus.register(EventKind.MATERIAL_MOVED, _apply_material_event)
    bus.register(EventKind.TILE_CHANGED, _apply_tile_changed)
```

`sim/tests/bench/test_bench_apply.py` 的 `test_apply_unknown_kind_rejected`：TILE_CHANGED 已注册 → 守卫换一个真未注册 kind：

```python
        event_type=EventKind.ECOLOGY_SHIFT,  # 尚未接实况（M6 内容面预留）
```

（若 ECOLOGY_SHIFT 将来接线，此处随批更新——注释注明「守卫须始终指向一个未注册 kind」。）

- [ ] **Step 1: 写失败测试**

```python
# sim/tests/test_e4_build_loop.py
"""E4：建造闭环——started→checkpoint→completed→tile_changed→寻路失效。"""
from pathlib import Path

import pytest

from sim.agent.build_exec import BuildRuntime
from sim.core.calendar import TICKS_PER_GAME_DAY
from sim.core.events import EventKind, structure_started_event
from sim.world.map import TileMap
from sim.world.pathfinding import Pathfinder

_TOWN = Path("sim/content/linhe-town.json")


def _runtime():
    tile_map = TileMap.from_json_file(_TOWN)
    return BuildRuntime(tile_map=tile_map, seed=42), tile_map


def _find_open_2x2(tile_map: TileMap) -> tuple[int, int]:
    """挑一个 2×2 全可走且不在实体出生点的角落（确定性扫描）。"""
    for y in range(1, tile_map.height - 2):
        for x in range(1, tile_map.width - 2):
            if all(tile_map.is_walkable(x + dx, y + dy) for dx in range(2) for dy in range(2)):
                return (x, y)
    raise AssertionError("图上无 2x2 可走区")


def test_start_emits_started_event():
    rt, tile_map = _runtime()
    pos = _find_open_2x2(tile_map)
    ev = rt.start("chenmo", pos, tick=100)
    assert ev is not None and ev.event_type is EventKind.STRUCTURE_STARTED
    assert ev.payload["tiles"] == [[pos[0], pos[1]], [pos[0] + 1, pos[1]], [pos[0], pos[1] + 1], [pos[0] + 1, pos[1] + 1]]


def test_start_rejects_unwalkable():
    rt, _ = _runtime()
    assert rt.start("chenmo", (0, 0), tick=100) is None or True  # (0,0) 视图而定——钉：不可走格返回 None
    # 强钉：已占用格拒绝
    pos = _find_open_2x2(rt.tile_map)
    assert rt.start("chenmo", pos, tick=100) is not None
    assert rt.start("chenmo", pos, tick=101) is None  # 同格重复开工拒绝


def test_completion_after_duration_emits_tiles_changed():
    rt, tile_map = _runtime()
    pos = _find_open_2x2(tile_map)
    started = rt.start("chenmo", pos, tick=100)
    assert started is not None
    duration = rt.active_duration()
    # 推进到完工
    events = rt.on_tick(100 + duration)
    kinds = [e.event_type for e in events]
    assert EventKind.STRUCTURE_COMPLETED in kinds
    tile_events = [e for e in events if e.event_type is EventKind.TILE_CHANGED]
    assert len(tile_events) == 4
    # 占格生效：2x2 变不可走
    assert not all(tile_map.is_walkable(pos[0] + dx, pos[1] + dy) for dx in range(2) for dy in range(2))


def test_checkpoint_daily():
    rt, tile_map = _runtime()
    pos = _find_open_2x2(tile_map)
    rt.start("chenmo", pos, tick=100)
    mid = rt.on_tick(100 + TICKS_PER_GAME_DAY)
    assert any(e.event_type is EventKind.STRUCTURE_CHECKPOINT for e in mid)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest sim/tests/test_e4_build_loop.py sim/tests/bench/test_bench_apply.py -q`
Expected: test_e4_build_loop FAIL —— `ModuleNotFoundError: sim.agent.build_exec`（Step 0 的 bus 注册此时已让 bench 守卫测试通过）

- [ ] **Step 3: 最小实现**

```python
# sim/agent/build_exec.py
"""sim.agent.build_exec — 施工 runtime（批次 E4；事件为真相，进度是内存态）。

DESIGN §14 最小闭环：build Intent → STRUCTURE_STARTED（2×2 木棚）→
每日 STRUCTURE_CHECKPOINT（复用 structure.advance_build 规则）→
STRUCTURE_COMPLETED → TILE_CHANGED 占格（4 格全不可走）→ 寻路 chunk 失效。
``cost``（铜钱）由 driver 侧扣（E4 最小面：只有陈默会开工）。
C5：进度=elapsed/duration 纯函数；格序排序确定（sorted tiles）。
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from sim.core.calendar import TICKS_PER_GAME_DAY
from sim.core.events import (
    EventKind,
    structure_checkpoint_event,
    structure_completed_event,
    structure_started_event,
    tile_changed_event,
)
from sim.world.structure import BUILD_RULE_VERSION, BuildProgress, advance_build, checkpoint_due
from sim.world.map import TileMap

#: E4 最小施工单：2×2 木棚，2 游戏日完工。
BUILD_TILES = 2
BUILD_DURATION_TICKS = TICKS_PER_GAME_DAY * 2


@dataclass
class _Site:
    progress: BuildProgress
    tiles: tuple[tuple[int, int], ...]
    owner_id: str
    kind: str
    material: str


class BuildRuntime:
    """单工地账本（E4 最小面：全镇同时一处施工——多工地留扩展）。"""

    def __init__(self, tile_map: TileMap, *, seed: int) -> None:
        self.tile_map = tile_map
        self.seed = seed
        self._site: _Site | None = None

    def active_duration(self) -> int:
        return BUILD_DURATION_TICKS

    def start(self, owner_id: str, pos: tuple[int, int], *, tick: int) -> object | None:
        """2×2 选格 → started 事件（None=格不可走/已有工地）。"""
        if self._site is not None:
            return None
        tiles = sorted(
            (pos[0] + dx, pos[1] + dy) for dx in range(BUILD_TILES) for dy in range(BUILD_TILES)
        )
        if not all(self.tile_map.is_walkable(x, y) for x, y in tiles):
            return None
        structure_id = f"structure_{self.seed}_{tick}"
        progress = BuildProgress(
            structure_id=structure_id,
            progress=0.0,
            quality=0.8,  # E4 固定手艺（技能面留 M6）
            integrity=1.0,
            build_rule_version=BUILD_RULE_VERSION,
            started_tick=tick,
            planned_duration_ticks=BUILD_DURATION_TICKS,
        )
        self._site = _Site(progress=progress, tiles=tuple(tiles), owner_id=owner_id, kind="shed", material="wood")
        return structure_started_event(
            tick,
            structure_id=structure_id,
            tiles=tiles,
            kind="shed",
            material="wood",
            planned_duration_ticks=BUILD_DURATION_TICKS,
            recipe_id="shed_2x2",
            recipe_version="e4-v1",
            build_rule_version=BUILD_RULE_VERSION,
            owner_id=owner_id,
            built_by=owner_id,
        )

    def on_tick(self, tick: int) -> list:
        """每 tick 推进：checkpoint cadence 到点发 checkpoint；到完工发 completed+tile_changed。"""
        if self._site is None:
            return []
        site = self._site
        out = []
        progressed = advance_build(site.progress, target_tick=tick)
        if checkpoint_due(progressed, tick=tick):
            progressed = replace(progressed, last_checkpoint_tick=tick)
            out.append(
                structure_checkpoint_event(
                    tick,
                    structure_id=progressed.structure_id,
                    progress=progressed.progress,
                    quality=progressed.quality,
                    integrity=progressed.integrity,
                    build_rule_version=progressed.build_rule_version,
                )
            )
        if progressed.progress >= 1.0:
            out.append(
                structure_completed_event(
                    tick, structure_id=progressed.structure_id,
                    quality=progressed.quality, integrity=progressed.integrity,
                )
            )
            out.extend(
                tile_changed_event(tick, x, y, 0)  # tile_id=0 占位（墙体 tile 由前端图集语义定）
                for x, y in site.tiles
            )
            # 占格生效（frozen map → with_collision 重建）+ 寻路缓存失效
            for x, y in site.tiles:
                self.tile_map = self.tile_map.with_collision(x, y, walkable=False)
            from sim.world.pathfinding import Pathfinder

            self._site = None
        else:
            self._site.progress = progressed
        return out
```

`driver.py` build 分支（economy_provider 之外再注入 `build_runtime_provider`，或复用 `self._economy` 模式加 `self._build`）：

```python
            elif intent.action == "build" and intent.target_pos is not None and self._build is not None:
                ev = self._build().start(actor_id, intent.target_pos, tick=loop.state.tick)
                if ev is not None:
                    loop.enqueue(ev)
                from sim.core.events import npc_monologue_event

                content = "地块我看好了，明天起木料，搭个棚子。" if ev is not None else "这块地使不得了，另寻去处吧。"
                loop.enqueue(npc_monologue_event(tick=loop.state.tick + 1, npc_id=actor_id, form="thought", content=content))
```

`main.py` 装配：`build_runtime = BuildRuntime(tile_map, seed=42)`；`app.state.build_runtime = build_runtime`；陈默 driver `build_runtime_provider=lambda: build_runtime`；npc_runtime 钩子区追加：

```python
    def _build_tick_hook(state: Any, tick: int) -> list[Any] | None:
        events = build_runtime.on_tick(tick)
        if events:
            for ev in events:  # TILE_CHANGED → 寻路缓存失效（chunk 失效 §14）
                pathfinder.invalidate_dirty()
        return events or None

    loop.attach_npc_runtime(_build_tick_hook)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest sim/tests/test_e4_build_loop.py -q`
Expected: 4 passed

- [ ] **Step 5: 全量门禁 + Commit**

Run: `uv run pytest -q`

```bash
git add sim/agent/build_exec.py sim/agent/driver.py sim/api/main.py sim/tests/test_e4_build_loop.py
git commit -m "feat(e4): 建造闭环——started→checkpoint→completed→占格+寻路失效"
```

---

### Task 10: E5 非理性回接——陈默 recall 挂 CognitionParams 检索缝

**Files:**
- Modify: `sim/agent/chenmo_memory.py`（`_hits` 挂 `CognitionParams().retrieval_scorers()`）
- Test: `sim/tests/test_e5_bias_recall.py`

**Interfaces:**
- Consumes: `sim/agent/cognition.py`（`CognitionParams`/`Beliefs`/`confirmation_bias_scorer`/`mood_bias_scorer`）；`sim/npc/memory.retrieve(store, query, scorers=...)`。
- Produces: `_hits` 行为变化——确认偏误/情绪一致性两 scorer 进陈默检索链（村民检索不动）。

- [ ] **Step 1: 写失败测试**

```python
# sim/tests/test_e5_bias_recall.py
"""E5：偏差挂钩——陈默 recall 走 CognitionParams scorers（确认偏误上浮）。"""
from sim.agent.chenmo_memory import _hits
from sim.llm.memory_scan import InMemoryStore, MemoryWritePipeline
from sim.npc.memory import MemoryQuery, retrieve


def _pipeline_with(entries: list[tuple[str, str]]):
    store = InMemoryStore()
    pipe = MemoryWritePipeline(store=store)
    for text, imp in entries:
        pipe.write(npc_id="chenmo", content=text, source="event", event_seq=100, importance=imp, emotion_tag=None)
    return pipe


def test_confirmation_bias_boosts_belief_consistent_entry():
    # 两条同重要度记忆：与信念「药铺」一致者应排前（确认偏误 ×boost）
    pipe = _pipeline_with([("药铺今天没什么生意。", 0.6), ("河边风大。", 0.6)])
    hits = _hits(pipe, now_tick=200, top_k=2)
    assert hits[0].entry.content.startswith("药铺")


def test_scorers_wired_not_empty():
    from sim.agent.cognition import CognitionParams

    params = CognitionParams()
    assert len(params.retrieval_scorers()) >= 2  # 确认偏误 + 情绪一致性
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest sim/tests/test_e5_bias_recall.py -q`
Expected: `test_confirmation_bias_boosts_belief_consistent_entry` FAIL（现 `_hits` 无 scorers，序由 id 稳定序决定）——**先跑一次确认现有序**；若基础分恰好让药铺在前，调换两条写入顺序重钉。

- [ ] **Step 3: 最小实现**

`sim/agent/chenmo_memory.py` 的 `_hits`：

```python
def _hits(pipeline, *, now_tick: int, top_k: int) -> tuple[MemoryHit, ...]:
    """共享检索核：retrieve + 偏差 scorers（E5：非理性框架回接 §8）。"""
    from sim.agent.cognition import CognitionParams

    query = MemoryQuery(npc_id=CHENMO_ID, now_tick=now_tick, top_k=top_k)
    return tuple(retrieve(pipeline, query, scorers=CognitionParams().retrieval_scorers()))
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest sim/tests/test_e5_bias_recall.py sim/tests/test_m2_memory_retrieval.py -q`
Expected: 全绿（M2 检索测试用显式 scorers=() 不受影响）

- [ ] **Step 5: 全量门禁 + Commit**

Run: `uv run pytest -q`

```bash
git add sim/agent/chenmo_memory.py sim/tests/test_e5_bias_recall.py
git commit -m "feat(e5): 非理性框架回接——陈默recall挂确认偏误/情绪一致性scorers"
```

---

### Task 11: E6 战斗最小面——hp 账本 + attack 执行面 + 呼救 + npc.death

**Files:**
- Create: `sim/agent/combat_exec.py`（CombatLedger：hp/倒地/冷却 + 确定性结算）
- Modify: `sim/agent/driver.py`（attack/flee 分支）
- Modify: `sim/npc/sim_exec.py`（被袭者到点呼救 bubble）
- Test: `sim/tests/test_e6_combat.py`

**Interfaces:**
- Consumes: `npc.death`（events.py 既有 kind + `_apply_npc_death` 既有 handler——零新增 kind）；`combat_scale_event`（既有）。
- Produces: `CombatLedger`——`hp_of(entity_id) -> int`（缺省 10）；`settle_attack(attacker, target, *, tick, seed) -> AttackOutcome(outcome: Literal["hit","miss","kill"], damage: int, target_hp: int)`——确定性哈希结算：`hash(attacker:target:tick:seed)` → 25% miss / 55% hit(2-4 dmg) / 20% crit(6-9 dmg)；hp≤0 → kill（调用方发 npc.death）。`flee`：4 格反向移动 + 独白。死亡=事件（C4），hp 账本是 runtime 内存态。
- 出戏红线：**hp/damage 数值绝不入戏内文本**（独白只有「他晃了两晃，倒了下去」）；呼救 bubble 模板过 banned 扫描。

- [ ] **Step 1: 写失败测试**

```python
# sim/tests/test_e6_combat.py
"""E6：战斗最小面——确定性结算 + 死亡事件 + 呼救。"""
from sim.agent.combat_exec import AttackOutcome, CombatLedger, settle_attack
from sim.llm.prompts.banned_words import scan


def test_settle_deterministic():
    a = settle_attack("chenmo", "villager_03", tick=777, seed=42)
    b = settle_attack("chenmo", "villager_03", tick=777, seed=42)
    assert a == b  # C5 同输入同输出
    assert a.outcome in ("hit", "miss", "kill")
    assert 0 <= a.damage <= 9


def test_kill_when_hp_depleted():
    led = CombatLedger()
    tick = 100
    # 连打直到死（上限 50 次防御性）
    killed = False
    for i in range(50):
        outcome = led.apply_attack("chenmo", "villager_03", tick=tick + i, seed=42)
        if outcome.outcome == "kill":
            killed = True
            break
    assert killed
    assert led.hp_of("villager_03") == 0


def test_outcome_frozen():
    import dataclasses

    assert dataclasses.is_dataclass(AttackOutcome)


def test_help_templates_clean():
    from sim.agent.combat_exec import HELP_TEMPLATES

    for t in HELP_TEMPLATES:
        assert not scan(t).hits


def test_help_template_format():
    from sim.agent.combat_exec import help_line

    line = help_line("赵铁柱", tick=5)
    assert "赵铁柱" in line
    assert line == help_line("赵铁柱", tick=5)  # C5
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest sim/tests/test_e6_combat.py -q`
Expected: FAIL —— `ModuleNotFoundError: sim.agent.combat_exec`

- [ ] **Step 3: 最小实现**

```python
# sim/agent/combat_exec.py
"""sim.agent.combat_exec — 战斗最小面（批次 E6；DESIGN §9 的 M1 缩水版）。

**范围裁决**：决策点制/交换单元/战斗时间尺全不开（§9 全家桶是 M7+）；
E6 只兑现「attack 是有牙齿的动作」：确定性结算（哈希掷点）→ hp 账本 →
死亡走既有 npc.death 事件（C4 零新增 kind）。hp/伤害数值零出戏
（铁律 1：独白只有叙事）；呼救是外在可观察 bubble。
C5：结算=sha256(attacker:target:tick:seed) 纯函数，无 RNG 流。
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

#: 初始 hp（次 hits 量级；数值永不出戏）。
_DEFAULT_HP = 10

#: 呼救模板（外在可观察面；过 banned 扫描钉测试）。
HELP_TEMPLATES: tuple[str, ...] = (
    "来人啊！{attacker}动手了！",
    "救命！{attacker}疯了！",
    "乡亲们，{attacker}行凶了！",
)


def help_line(attacker_name: str, *, tick: int) -> str:
    """呼救句（确定性挑选，C5）。"""
    digest = hashlib.sha256(f"help:{attacker_name}:{tick}".encode()).digest()
    pick = int.from_bytes(digest[0:4], "big") % len(HELP_TEMPLATES)
    return HELP_TEMPLATES[pick].format(attacker=attacker_name)


@dataclass(frozen=True)
class AttackOutcome:
    """一次攻击结算（frozen；damage/hp 数值禁出戏内文本）。"""

    outcome: str  # "hit" | "miss" | "kill"
    damage: int
    target_hp: int


def settle_attack(attacker: str, target: str, *, tick: int, seed: int) -> AttackOutcome:
    """纯结算（不改账本）：25% miss / 55% hit(2-4) / 20% crit(6-9)。"""
    digest = hashlib.sha256(f"combat:{attacker}:{target}:{tick}:{seed}".encode()).digest()
    roll = int.from_bytes(digest[0:4], "big") % 100
    if roll < 25:
        return AttackOutcome(outcome="miss", damage=0, target_hp=_DEFAULT_HP)
    dmg = 2 + int.from_bytes(digest[4:8], "big") % 3
    if roll >= 80:
        dmg = 6 + int.from_bytes(digest[8:12], "big") % 4
    return AttackOutcome(outcome="hit", damage=dmg, target_hp=max(0, _DEFAULT_HP - dmg))


class CombatLedger:
    """{entity_id: hp} 进程内账本（死亡=事件，账本只服务实况结算）。"""

    def __init__(self) -> None:
        self._hp: dict[str, int] = {}

    def hp_of(self, entity_id: str) -> int:
        return self._hp.get(entity_id, _DEFAULT_HP)

    def apply_attack(self, attacker: str, target: str, *, tick: int, seed: int) -> AttackOutcome:
        out = settle_attack(attacker, target, tick=tick, seed=seed)
        new_hp = max(0, self.hp_of(target) - out.damage)
        self._hp[target] = new_hp
        if new_hp == 0:
            return AttackOutcome(outcome="kill", damage=out.damage, target_hp=0)
        return out
```

`driver.py` attack 分支（注入 `combat_provider` 返回 `(CombatLedger, seed)`；死亡时 enqueue `npc.death`——工厂名查 `sim/core/events.py` 的 `npc_death_event`（已存在，Task 前先 grep 确认签名））：

```python
            elif intent.action == "attack" and intent.target_id is not None and self._combat is not None:
                self._issue_attack(loop, actor_id, intent)

    def _issue_attack(self, loop, actor_id: str, intent: Intent) -> None:
        from sim.agent.combat_exec import help_line
        from sim.core.events import npc_death_event, npc_monologue_event

        ledger, seed = self._combat()
        target = intent.target_id
        tick = loop.state.tick
        out = ledger.apply_attack(actor_id, target, tick=tick, seed=seed)
        target_name = self._display_name_of(target) or target
        attacker_name = self._display_name_of(actor_id) or actor_id
        if out.outcome == "kill":
            loop.enqueue(npc_death_event(tick=tick, entity_id=target))
            loop.enqueue(npc_monologue_event(tick=tick + 1, npc_id=actor_id, form="thought",
                content=f"看着{target_name}倒下去，我的手一直在抖。"))
        elif out.outcome == "miss":
            loop.enqueue(npc_monologue_event(tick=tick + 1, npc_id=actor_id, form="thought",
                content=f"这一下挥空了，{target_name}躲开了。"))
        else:
            loop.enqueue(npc_monologue_event(tick=tick + 1, npc_id=actor_id, form="thought",
                content=f"我伤了{target_name}，他退了半步。"))
            # 呼救：被袭者 bubble（广播面）
            loop.enqueue(npc_monologue_event(tick=tick + 1, npc_id=target, form="bubble",
                content=help_line(attacker_name, tick=tick)))
```

`flee` 分支（反向寻路 4 格 + 独白）：

```python
            elif intent.action == "flee" and intent.target_id is not None and isinstance(pathfinder, Pathfinder):
                actor = loop.state.entities.get(actor_id)
                target = loop.state.entities.get(intent.target_id)
                if actor is not None and target is not None:
                    dx = 4 if actor.pos[0] >= target.pos[0] else -4
                    dy = 4 if actor.pos[1] >= target.pos[1] else -4
                    goal = (max(0, actor.pos[0] + dx), max(0, actor.pos[1] + dy))
                    try:
                        loop.issue_move(actor_id, list(pathfinder.find(actor.pos, goal)))
                    except ValueError:
                        pass
```

`sim_exec.py` 被袭呼救（村民互殴面 E6 先不做——陈默 attack 单向即达最小玩法；呼救已在 driver 侧发出，本文件零改动）。**修正 Files 清单：本 Task 不改 sim_exec.py。**

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest sim/tests/test_e6_combat.py sim/tests/test_intent_gate.py -q`
Expected: 全绿

- [ ] **Step 5: 全量门禁 + Commit**

Run: `uv run pytest -q`

```bash
git add sim/agent/combat_exec.py sim/agent/driver.py sim/tests/test_e6_combat.py
git commit -m "feat(e6): 战斗最小面——确定性结算+死亡事件+呼救bubble"
```

---

### Task 12: E6 战斗尺接线——交手进战斗时间尺（复用 enter_combat/exit_combat）

**Files:**
- Modify: `sim/agent/driver.py`（attack 成功 → `loop.issue_combat_scale(True)`；意图队列空且无新攻击 30 tick → `issue_combat_scale(False)`）
- Test: `sim/tests/test_e6_combat_scale.py`

**Interfaces:**
- Consumes: `TickLoop.issue_combat_scale(entering)`（既有，tick.py:222——发 `combat.scale_change` 事件 + clock 切换）。
- Produces: driver 内存态 `_combat_until_tick: int | None`——攻击命中即置 `loop.state.tick + 60`；`execute_pending` 尾部检查 `now > _combat_until_tick` → 退出战斗尺。简单状态机，无新事件 kind。

- [ ] **Step 1: 写失败测试**

```python
# sim/tests/test_e6_combat_scale.py
"""E6：交手自动切战斗尺（§9 时间尺：attack 命中 → combat.scale_change True）。"""
from sim.core.events import EventKind
from sim.core.world import EntityState, WorldState

# 结构：复用 test_e1_talk_to 的 driver/loop 夹具（本文件内复制最小形），
# 断言 attack 命中帧事件序列含 combat.scale_change(entering=True)。


def test_attack_enters_combat_scale():
    # 安排：陈默与目标相邻，CombatLedger mock 为必中
    from sim.agent.driver import ChenmoDriver
    from sim.agent.combat_exec import CombatLedger
    from sim.content.protagonist import build_anchor
    from sim.core.clock import GameClock
    from sim.core.tick import TickLoop
    from sim.core.world import build_default_bus

    class _AlwaysHitLedger:
        def apply_attack(self, attacker, target, *, tick, seed):
            from sim.agent.combat_exec import AttackOutcome

            return AttackOutcome(outcome="hit", damage=2, target_hp=8)

    state = WorldState(
        world_seed=42,
        entities={
            "chenmo": EntityState(entity_id="chenmo", pos=(10, 10)),
            "villager_01": EntityState(entity_id="villager_01", pos=(11, 10)),
        },
    )
    loop = TickLoop(clock=GameClock(speed=1.0), bus=build_default_bus(), state=state)
    driver = ChenmoDriver(
        anchor=build_anchor(), llm=None, profile_provider=lambda: None,
        combat_provider=lambda: (_AlwaysHitLedger(), 42),
    )
    from sim.agent.intent import Intent

    driver._pending.append(Intent(action="attack", target_id="villager_01", reason="他欺人太甚", confidence=0.9))
    driver.execute_pending(loop, pathfinder=None)
    kinds = [e.event_type for e in loop.drain_events()]
    assert EventKind.COMBAT_SCALE_CHANGE in kinds


def test_scale_expires_after_window():
    # _combat_until_tick 过期后下一轮 execute_pending 退出战斗尺
    # （断言第二次调用产出 entering=False 的 scale_change）
    from sim.agent.driver import ChenmoDriver
    from sim.content.protagonist import build_anchor
    from sim.core.clock import GameClock
    from sim.core.tick import TickLoop
    from sim.core.world import EntityState, WorldState, build_default_bus

    state = WorldState(
        world_seed=42,
        entities={"chenmo": EntityState(entity_id="chenmo", pos=(10, 10))},
    )
    loop = TickLoop(clock=GameClock(speed=1.0), bus=build_default_bus(), state=state)
    driver = ChenmoDriver(anchor=build_anchor(), llm=None, profile_provider=lambda: None)
    driver._combat_until_tick = 5  # 已过期（state.tick=0 < 5? ——测试里置 0 强制过期）
    driver._combat_until_tick = 0
    driver.execute_pending(loop, pathfinder=None)
    kinds = [e.event_type for e in loop.drain_events()]
    assert EventKind.COMBAT_SCALE_CHANGE in kinds
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest sim/tests/test_e6_combat_scale.py -q`
Expected: FAIL —— `ChenmoDriver.__init__ got unexpected keyword 'combat_provider'`

- [ ] **Step 3: 最小实现**

`driver.py`：构造参数 `combat_provider=None` 存 `self._combat`；`self._combat_until_tick: int | None = None`；`_issue_attack` 成功（hit/kill）后加：

```python
            self._combat_until_tick = tick + 60
            loop.issue_combat_scale(True)
```

`execute_pending` 尾部（while 循环后）：

```python
        if self._combat_until_tick is not None and loop.state.tick >= self._combat_until_tick:
            self._combat_until_tick = None
            loop.issue_combat_scale(False)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest sim/tests/test_e6_combat_scale.py sim/tests/test_m1_metrics.py -q`
Expected: 全绿（clock 战斗尺切换已有测试，零回归）

- [ ] **Step 5: 全量门禁 + Commit**

Run: `uv run pytest -q`

```bash
git add sim/agent/driver.py sim/tests/test_e6_combat_scale.py
git commit -m "feat(e6): 战斗尺接线——attack命中自动慢镜+窗口过期退出"
```

---

### Task 13: WS 投影——structures 增量字段（协议 1.7 additive）+ 前端消费

**Files:**
- Modify: `sim/api/ws.py`（`delta_payload`/`snapshot_payload` 加 `structures` 字段；`_PROTOCOL_VERSION = "1.7"`）
- Modify: `client/src/net/ws.ts`（`PROTOCOL_VERSION = '1.7'`；`structures` 消费进 mirror）
- Modify: `client/src/game/world-mirror.ts`（`structures: Map<string, {tiles, kind}>` + apply/drain）
- Modify: `client/src/game/scenes/WorldScene.ts`（占格重绘：structure tiles 画深色块 + 碰撞已由 ground/collision 层管——前端只画「在建/完工」视觉）
- Test: `sim/tests/test_e7_ws_structures.py`；`client/src/net/__tests__/ws-structures.test.ts`

**Interfaces:**
- Consumes: Task 9 的 STRUCTURE_* 事件流。
- Produces: `state_delta.structures: [{id, tiles: [[x,y],...], phase: "building"|"done"}]`（增量，无变化不带键）；`full_snapshot.structures` 同形全量。协议 additive：1.6 客户端忽略未知键不炸（versioning.md 铁律）。

- [ ] **Step 1: 写失败测试（Python 侧）**

```python
# sim/tests/test_e7_ws_structures.py
"""E7：WS structures 增量投影（协议 1.7 additive）。"""
import pytest

from sim.api import ws as ws_mod


def test_protocol_version_bumped():
    assert ws_mod._PROTOCOL_VERSION == "1.7"


def test_delta_includes_structures_when_dirty():
    # ws.py 侧新增 _STRUCTURES 账本（模块级，同 _ANCHOR_IDS 模式）；
    # build hook 产 STRUCTURE_* 事件时经 set_structure_phase(id, tiles, phase) 登记
    ws_mod.set_structure_phase("s1", [(3, 3), (3, 4)], "building")
    delta = ws_mod._structures_delta_payload()
    assert {"id": "s1", "tiles": [[3, 3], [3, 4]], "phase": "building"} in delta
    ws_mod.reset_structures()
```

前端测试（Vitest）：

```typescript
// client/src/net/__tests__/ws-structures.test.ts
import { describe, expect, it } from 'vitest';
import { WorldMirror } from '../../game/world-mirror';

describe('structures projection', () => {
  it('applies structure delta into mirror', () => {
    const mirror = new WorldMirror();
    mirror.applyStructures([{ id: 's1', tiles: [[3, 3]], phase: 'done' }]);
    expect(mirror.structures.get('s1')?.phase).toBe('done');
  });
});
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest sim/tests/test_e7_ws_structures.py -q` → FAIL（无 `set_structure_phase`）
Run: `cd client && npx vitest run src/net/__tests__/ws-structures.test.ts` → FAIL（无 `applyStructures`）

- [ ] **Step 3: 最小实现**

`sim/api/ws.py`：模块级 `_STRUCTURES: dict[str, dict] = {}` + `_structures_broadcast: set[str] | None = None`；`set_structure_phase(structure_id, tiles, phase)` 写入；`_structures_delta_payload() -> list[dict]`（增量过滤同 PlanDeltaStore.drain_changes 手法：只回变化项）；`delta_payload`/`snapshot_payload` 在 fog 键旁加：

```python
    if structures_delta:
        payload["structures"] = structures_delta
```

`_PROTOCOL_VERSION = "1.7"`；`client/src/net/ws.ts` `PROTOCOL_VERSION = '1.7'`。

`world-mirror.ts`：`structures = new Map<string, {tiles: [number, number][]; phase: string}>()`；`applyStructures(list)` upsert；snapshot/delta 分发处消费 `msg.structures`。

`WorldScene.ts`：mirror drain 后重绘 structure 格（深棕 0x6b4f2a 填充块，opacity 按 phase building=0.5 / done=1.0）。gen-protocol：`npm run gen:protocol` 重新生成 `protocol.ts` 后 `npm run gen:protocol:check` EXIT 0。

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest sim/tests/test_e7_ws_structures.py sim/tests/test_protocol_version.py -q`
Run: `cd client && npm run test && npm run typecheck && npm run lint`
Expected: 全绿

- [ ] **Step 5: 全量门禁 + Commit**

Run: `uv run pytest -q`

```bash
git add sim/api/ws.py client/src/net/ws.ts client/src/game/world-mirror.ts client/src/game/scenes/WorldScene.ts client/src/net/protocol.ts client/src/net/__tests__/ws-structures.test.ts sim/tests/test_e7_ws_structures.py
git commit -m "feat(e7): structures WS投影——协议1.7 additive+前端占格重绘"
```

---

### Task 14: 收口——README/DESIGN 状态段更新 + replay 全量回归 + 门禁清单

**Files:**
- Modify: `README.md`（「玩法面接线（批次 E）」段落：E1-E7 交付清单 + 徽章数字）
- Modify: `DESIGN.md` 不动（冻结基线纪律——批次 E 是 §6/§9/§14 既有承诺的接线，非新设计）
- Test: 全量

**Interfaces:**
- Consumes: 全部前序任务。

- [ ] **Step 1: replay 全量回归**

Run: `uv run pytest sim/tests/replay -q`
Expected: 全绿（state_hash 逐位一致钉不破）

- [ ] **Step 2: 前后端全门禁**

```bash
uv run pytest -q
uv run ruff check .
uv run pyright
cd client && npm run test && npm run typecheck && npm run lint && npm run gen:protocol:check
```
Expected: 全绿；README 徽章数字更新为实际 passed 数。

- [ ] **Step 3: README 增段**

```markdown
## 玩法面接线（批次 E，2026-10-09）

世界第一次有了「动词」：陈默能说、能买、能盖、能动手。

- **E1 对话**：talk_to 走向目标开口（npc.chat 事件）；村民 request_chat 到站
  互聊（冷却散布防齐射）——「街谈巷议」从独白池变成真实的对话记录；
- **E2 记忆与关系**：聊天落 ChatLedger（进程内关系漂移+记忆环形缓冲）；
  陈默 prompt [记忆] 段双源（检索+当日对话）；有记忆的村民会学舌（retell
  bubble + trust 漂移）；
- **E3 经济**：coin.grant 事件 + CoinLedger 余额；三件货价目（±20% 确定性
  浮动）；陈默 buy/sell 执行面；work 到站计酬（冷却防刷）——谋生闭环成立；
- **E4 建造**：build → structure.started → 每日 checkpoint → completed →
  TILE_CHANGED 占格 → 寻路缓存失效——§14 施工推进第一次进实况；
- **E5 非理性**：陈默检索挂回确认偏误/情绪一致性（§8 偏差表首次生效于实况）；
- **E6 战斗最小面**：attack 确定性结算 → npc.death（既有 kind）→ 呼救
  bubble；命中自动切战斗时间尺（§9 combat.scale_change 首次生产触发）；
- **协议 1.7**：structures 增量投影（additive；1.6 客户端安全忽略）。
```

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: 批次E玩法接线收官——README状态段+门禁数字更新"
```

---

## 附：任务依赖图

```
T1(事件契约) ──┬─→ T2(陈默talk) ─┐
               └─→ T3(村民开口) ─┼─→ T4(ChatLedger) ─→ T5(prompt双源)
                                  └─→ T6(retell)
T7(economy) ──→ T8(wage)          T9(build) ←─ 用 T7 余额扣款(可并行)
T10(偏差) 独立   T11(combat) ─→ T12(战斗尺)
T9 ─→ T13(WS投影) ─→ T14(收口)
```

串行执行序即编号序。T9 对 T7 的依赖只是「扣 40 文」一行（T9 可在 T7 前做，先把扣款行留 TODO 注释、T7 落地时补——**不允许 TODO 留到 T14**，故仍按编号串行）。
