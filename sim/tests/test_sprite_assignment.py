"""test_sprite_assignment.py — 外观分配回归钉（2026-10-12 D1-D5 接入）。

裁决兑现（docs/data/god-reuse-final.md §5，D5 最小步=外观面角色分层）:
- 17 张 GOD 古风角色 sheet 已落 client/public/assets/sprites/god_villager_*.png
- 外观分配 = entity_id 确定性纯函数（sha256，C5 无 RNG）：
  chenmo 恒 "protagonist"（中性键，防内部 id 词面出站）；
  villager_NN → god_villager_<slug>（17 张哈希轮转）
- sprite 字段是前端 texture key（协议自由 string，零 schema 变更）
- 出站安全：分配函数只吃 entity_id，不吃世界状态——无出戏泄漏面
"""

from __future__ import annotations

from sim.api.ws import sprite_name_of
from sim.content.villagers import VILLAGER_IDS, sprite_for_entity


def test_protagonist_neutral_key():
    """主角恒中性 texture key "protagonist"——出戏红线：快照文本禁含
    内部 id 词面 "chenmo"（test_ws_gateway W 系列钉），sprite 值同守。"""
    assert sprite_for_entity("chenmo") == "protagonist"


def test_villager_gets_god_texture():
    """村民分派 GOD 皮（god_villager_ 前缀）。"""
    s = sprite_for_entity("villager_01")
    assert s.startswith("god_villager_")


def test_deterministic_and_stable():
    """同 id 恒同皮（重放一致 C5）；不同村民可同皮（17<50 允许轮转复用）。"""
    assert sprite_for_entity("villager_07") == sprite_for_entity("villager_07")
    sprites = {sprite_for_entity(v) for v in VILLAGER_IDS}
    assert 1 < len(sprites) <= 17


def test_ws_sprite_name_of_wiring():
    """ws.py 出站口走同一函数（单一真相源）：快照/delta 同皮。"""
    assert sprite_name_of("chenmo") == "protagonist"
    s = sprite_name_of("villager_03")
    assert s.startswith("god_villager_")


def test_animals_never_get_villager_body():
    """创世动物不得落到人形外观池（2026-10-20 实测 bug）。

    灰/黑子/鸦是 GENESIS_ENTITIES 成员，会走 ws.py `_actor_rows` 的主循环，
    此前一律落到 `sprite_for_entity` 的 GOD 村民池 → 猫狗鸦被渲染成人形村民。
    钉住：三只动物各自拿到 `fauna_` 前缀的专属剪影，且**不在** GOD 池内。
    """
    from sim.content.villagers import GOD_SPRITE_POOL

    expected = {"cat_grey": "fauna_cat", "dog_black": "fauna_dog", "raven": "fauna_raven"}
    for entity_id, sprite in expected.items():
        assert sprite_for_entity(entity_id) == sprite, entity_id
        assert sprite not in GOD_SPRITE_POOL, entity_id
        assert sprite_name_of(entity_id) == sprite, entity_id


def test_unknown_non_villager_still_has_safe_fallback():
    """非动物、非主角的未知 id 仍走 GOD 池（零行为回退；只有显式动物表改道）。"""
    from sim.content.villagers import GOD_SPRITE_POOL

    assert sprite_for_entity("some_new_entity") in GOD_SPRITE_POOL
