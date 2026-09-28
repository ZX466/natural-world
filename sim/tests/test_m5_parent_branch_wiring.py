"""M5-D3-a 生产侧接线钉子（裁 25-B②）：parent_branch_id 走通 WorldEvent → store 行。

持久层（D3-a）已打通 `append` 读 `event["parent_branch_id"]` + validate_store_row
optional-str 校验；本钉子钉「事件模型侧的缝已接」——架构域（Claude）接线承诺，
opencode 的 fork/克隆不依赖本字段生产侧（D3-b 回执明示），故此钉是形状契约：
  1. WorldEvent 有 parent_branch_id 字段（缺省 None，frozen 不破）；
  2. to_store_dict() 透传该键（None 时也带键——与 parent_seq 同形，append 端
     `event.get()` 读 None 即不落跨分支引用）；
  3. 事件工厂（world_create_event）不带该参数——跨分支谱系引用只在 fork 场景
     由架构域构造（不是工厂职责），防误用。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sim.core.events import EventKind, WorldEvent, world_create_event


class TestParentBranchIdWiring:
    def test_field_exists_default_none_frozen(self):
        ev = WorldEvent(tick=1, event_type=EventKind.WORLD_CREATE)
        assert ev.parent_branch_id is None
        with pytest.raises(ValidationError):
            ev.parent_branch_id = "main"

    def test_to_store_dict_passes_key_through(self):
        ev = WorldEvent(
            tick=1,
            event_type=EventKind.WORLD_CREATE,
            parent_branch_id="parent-branch",
        )
        row = ev.to_store_dict()
        assert row["parent_branch_id"] == "parent-branch"

    def test_to_store_dict_none_still_carries_key(self):
        """None 也带键（append 端 event.get() 读 None = 本分支引用，同 parent_seq 形）。"""
        ev = WorldEvent(tick=1, event_type=EventKind.WORLD_CREATE)
        assert "parent_branch_id" in ev.to_store_dict()
        assert ev.to_store_dict()["parent_branch_id"] is None

    def test_factory_does_not_accept_parent_branch(self):
        """工厂不收 parent_branch_id——跨分支谱系引用只在 fork 场景由架构域构造。"""
        import inspect

        sig = inspect.signature(world_create_event)
        assert "parent_branch_id" not in sig.parameters
