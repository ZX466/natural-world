"""M4-D2a T1 钉子 — 建造事件族 payload 契约（m3-preplan §2 C1/C2/C3/C5/C7）。

覆盖：kind 全登记（无漏登记）、extra=forbid、数值域与 bool 冒充、标识符
字符集/长度、cause/reason 枚举与 note 缺席、工厂拒绝可迭代洗白。
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from sim.core.events import (
    EventKind,
    MaterialMovedPayload,
    StructureCheckpointPayload,
    StructureCollapsedPayload,
    StructureCompletedPayload,
    StructureRemovedPayload,
    StructureStartedPayload,
    material_moved_event,
    structure_checkpoint_event,
    structure_collapsed_event,
    structure_completed_event,
    structure_removed_event,
    structure_started_event,
)
from sim.core.persistence.event_validation import (
    PAYLOAD_MODELS,
    EventValidationError,
    validate_store_row,
)

_BUILD = {
    "structure_id": "hut-1",
    "tiles": ((0, 0), (1, 0)),
    "kind": "wood_hut",
    "material": "wood",
    "planned_duration_ticks": 86_400,
    "recipe_id": "hut.v1",
    "recipe_version": "1",
    "build_rule_version": "1",
}


class TestRegistration:
    def test_every_kind_has_payload_model(self) -> None:
        assert set(PAYLOAD_MODELS) == set(EventKind)

    @pytest.mark.parametrize(
        "kind",
        [
            EventKind.STRUCTURE_STARTED,
            EventKind.STRUCTURE_CHECKPOINT,
            EventKind.STRUCTURE_COMPLETED,
            EventKind.STRUCTURE_COLLAPSED,
            EventKind.STRUCTURE_REMOVED,
            EventKind.MATERIAL_MOVED,
        ],
    )
    def test_structure_kind_registered(self, kind: EventKind) -> None:
        assert PAYLOAD_MODELS[kind].model_config.get("extra") == "forbid"


class TestStructureStartedPayload:
    def test_canonicalizes_tiles_and_supports(self) -> None:
        payload = StructureStartedPayload(
            **{
                **_BUILD,
                "tiles": ((1, 0), (0, 0)),
                "supported_by": ("wall-2", "wall-1"),
            }
        )

        assert payload.tiles == ((0, 0), (1, 0))
        assert payload.supported_by == ("wall-1", "wall-2")

    @pytest.mark.parametrize("tiles", [(), ((0, 0), (0, 0))])
    def test_rejects_empty_or_duplicate_tiles(self, tiles: tuple[Any, ...]) -> None:
        with pytest.raises(ValidationError):
            StructureStartedPayload(**{**_BUILD, "tiles": tiles})

    def test_rejects_self_support(self) -> None:
        with pytest.raises(ValidationError, match="自身"):
            StructureStartedPayload(**_BUILD, supported_by=("hut-1",))

    @pytest.mark.parametrize("field", ["structure_id", "kind", "material", "recipe_id"])
    def test_rejects_invalid_identifier(self, field: str) -> None:
        with pytest.raises(ValidationError):
            StructureStartedPayload(**{**_BUILD, field: "坏 id/注入"})

    def test_rejects_too_long_identifier(self) -> None:
        with pytest.raises(ValidationError):
            StructureStartedPayload(**{**_BUILD, "structure_id": "x" * 65})

    def test_rejects_bool_tile_coordinate(self) -> None:
        with pytest.raises(ValidationError):
            StructureStartedPayload(**{**_BUILD, "tiles": ((True, 0),)})

    def test_rejects_bool_duration(self) -> None:
        with pytest.raises(ValidationError):
            StructureStartedPayload(**{**_BUILD, "planned_duration_ticks": True})

    def test_forbids_note(self) -> None:
        with pytest.raises(ValidationError):
            StructureStartedPayload(**_BUILD, note="玩家留言")  # type: ignore[call-arg]


class TestProgressPayloads:
    @pytest.mark.parametrize("field", ["progress", "quality", "integrity"])
    @pytest.mark.parametrize("value", [-0.1, 1.1, float("nan"), float("inf")])
    def test_checkpoint_rejects_out_of_domain(self, field: str, value: float) -> None:
        payload = {
            "structure_id": "hut-1",
            "progress": 0.5,
            "quality": 0.5,
            "integrity": 1.0,
            "build_rule_version": "1",
        }
        with pytest.raises(ValidationError):
            StructureCheckpointPayload(**{**payload, field: value})

    def test_checkpoint_rejects_bool_progress(self) -> None:
        with pytest.raises(ValidationError):
            StructureCheckpointPayload(
                structure_id="hut-1",
                progress=True,
                quality=0.5,
                integrity=1.0,
                build_rule_version="1",
            )

    def test_completed_requires_full_integrity_domain(self) -> None:
        with pytest.raises(ValidationError):
            StructureCompletedPayload(structure_id="hut-1", quality=0.8, integrity=1.2)

    def test_collapsed_cause_is_closed_enum(self) -> None:
        with pytest.raises(ValidationError):
            StructureCollapsedPayload(
                structure_id="hut-1",
                cause="because",  # type: ignore[arg-type]
                support_path=(),
                integrity=0.0,
            )

    def test_removed_reason_is_closed_enum(self) -> None:
        with pytest.raises(ValidationError):
            StructureRemovedPayload(
                structure_id="hut-1",
                reason="whatever",  # type: ignore[arg-type]
            )


class TestMaterialMovedPayload:
    def _payload(self, **overrides: Any) -> dict[str, Any]:
        payload = {
            "transfer_id": "t-1",
            "material_id": "wood",
            "quantity": 2.0,
            "from_ref": "world:stockpile",
            "to_ref": "structure:hut-1",
            "reason": "build_consumed",
            "structure_id": "hut-1",
            "recipe_id": "hut.v1",
        }
        return {**payload, **overrides}

    @pytest.mark.parametrize("quantity", [0.0, -1.0, float("nan"), float("inf")])
    def test_rejects_non_positive_or_non_finite(self, quantity: float) -> None:
        with pytest.raises(ValidationError):
            MaterialMovedPayload(**self._payload(quantity=quantity))

    def test_rejects_bool_quantity(self) -> None:
        with pytest.raises(ValidationError):
            MaterialMovedPayload(**self._payload(quantity=True))

    def test_rejects_invalid_ref(self) -> None:
        with pytest.raises(ValidationError):
            MaterialMovedPayload(**self._payload(from_ref="free text"))

    def test_reason_is_closed_enum(self) -> None:
        with pytest.raises(ValidationError):
            MaterialMovedPayload(**self._payload(reason="teleport"))

    def test_forbids_note(self) -> None:
        with pytest.raises(ValidationError):
            MaterialMovedPayload(**self._payload(note="x"))


class TestFactories:
    def test_started_event_shape(self) -> None:
        event = structure_started_event(tick=10, **_BUILD)

        assert event.event_type is EventKind.STRUCTURE_STARTED
        assert event.payload["tiles"] == [[0, 0], [1, 0]]
        assert "note" not in event.payload

    def test_checkpoint_event_shape(self) -> None:
        event = structure_checkpoint_event(
            tick=86_400,
            structure_id="hut-1",
            progress=0.5,
            quality=0.4,
            integrity=1.0,
            build_rule_version="1",
        )
        assert event.event_type is EventKind.STRUCTURE_CHECKPOINT
        assert event.payload["progress"] == pytest.approx(0.5)

    def test_completed_collapsed_removed_material_shapes(self) -> None:
        completed = structure_completed_event(
            tick=86_400, structure_id="hut-1", quality=0.4, integrity=1.0
        )
        collapsed = structure_collapsed_event(
            tick=90_000, structure_id="hut-1", cause="support_lost", support_path=("wall-1",)
        )
        removed = structure_removed_event(tick=90_001, structure_id="hut-1", reason="demolished")
        moved = material_moved_event(
            tick=90_001,
            transfer_id="t-1",
            material_id="wood",
            quantity=1.0,
            from_ref="structure:hut-1",
            to_ref="npc:chenmo",
            reason="demolish_yield",
            structure_id="hut-1",
        )

        assert completed.event_type is EventKind.STRUCTURE_COMPLETED
        assert collapsed.payload["cause"] == "support_lost"
        assert removed.payload["reason"] == "demolished"
        assert moved.payload["from_ref"] == "structure:hut-1"

    @pytest.mark.parametrize("tiles", ["ab", b"ab", {0: 0, 1: 1}])
    def test_started_factory_rejects_iterable_wash(self, tiles: Any) -> None:
        with pytest.raises((TypeError, ValidationError)):
            structure_started_event(tick=1, **{**_BUILD, "tiles": tiles})


class TestStoreRowValidation:
    def test_started_row_accepts(self) -> None:
        row = structure_started_event(tick=1, **_BUILD).to_store_dict()
        validate_store_row(row)

    def test_started_row_rejects_note_with_payload_fingerprint(self) -> None:
        row = structure_started_event(tick=1, **_BUILD).to_store_dict()
        row["payload"]["note"] = "夹带"  # type: ignore[index]

        with pytest.raises(EventValidationError) as exc_info:
            validate_store_row(row)
        assert "payload 校验失败" in str(exc_info.value)

    def test_material_row_rejects_extra_key(self) -> None:
        row = material_moved_event(
            tick=1,
            transfer_id="t-1",
            material_id="wood",
            quantity=1.0,
            from_ref="world:stockpile",
            to_ref="structure:hut-1",
            reason="build_consumed",
        ).to_store_dict()
        row["payload"]["surprise"] = 1  # type: ignore[index]

        with pytest.raises(EventValidationError, match="payload 校验失败"):
            validate_store_row(row)
