"""M4-D2c T1 钉子 — 内存承重图不变量 + 级联按帧摊还。"""

from __future__ import annotations

import pytest

from sim.core.events import EventKind
from sim.world.structure import StructurePhase, StructureSnapshot
from sim.world.support_graph import (
    CASCADE_EVENT_BUDGET_PER_FRAME,
    SUPPORT_GRAPH_ACCEPTANCE_NODES,
    GraphError,
    advance_cascade,
    build_support_graph,
    start_cascade,
)


def node(
    structure_id: str,
    *,
    supported_by: tuple[str, ...] = (),
    phase: StructurePhase = StructurePhase.ACTIVE,
    load_bearing: bool = True,
) -> StructureSnapshot:
    return StructureSnapshot(
        structure_id=structure_id,
        tiles=((0, 0),),
        kind="stone_wall",
        material="stone",
        phase=phase,
        load_bearing=load_bearing,
        supported_by=supported_by,
    )


class TestSupportGraph:
    def test_builds_sorted_dependents(self) -> None:
        graph = build_support_graph(
            [
                ("main", node("base")),
                ("main", node("wall-2", supported_by=("base",))),
                ("main", node("wall-1", supported_by=("base",))),
            ]
        )

        assert graph.branch_id == "main"
        assert graph.dependents["base"] == ("wall-1", "wall-2")

    def test_rejects_mixed_branch(self) -> None:
        with pytest.raises(GraphError, match="分支"):
            build_support_graph([("main", node("a")), ("fork", node("b", supported_by=("a",)))])

    def test_rejects_duplicate_structure_id(self) -> None:
        with pytest.raises(GraphError, match="重复"):
            build_support_graph([("main", node("a")), ("main", node("a"))])

    def test_rejects_self_and_missing_edges(self) -> None:
        with pytest.raises(GraphError, match="自身"):
            build_support_graph([("main", node("a", supported_by=("a",)))])
        with pytest.raises(GraphError, match="不存在"):
            build_support_graph([("main", node("a", supported_by=("ghost",)))])

    def test_duplicate_edge_rejected_by_snapshot_layer(self) -> None:
        with pytest.raises(ValueError, match="重复"):
            node("b", supported_by=("a", "a"))

    def test_rejects_cycle(self) -> None:
        with pytest.raises(GraphError, match="环"):
            build_support_graph(
                [
                    ("main", node("a", supported_by=("b",))),
                    ("main", node("b", supported_by=("a",))),
                ]
            )

    @pytest.mark.parametrize("phase", [StructurePhase.PLANNED, StructurePhase.BUILDING])
    def test_planned_or_building_cannot_support(self, phase: StructurePhase) -> None:
        with pytest.raises(GraphError, match="承重"):
            build_support_graph(
                [
                    ("main", node("base", phase=phase)),
                    ("main", node("top", supported_by=("base",))),
                ]
            )


class TestCascade:
    def test_stable_order_and_support_paths(self) -> None:
        graph = build_support_graph(
            [
                ("main", node("base")),
                ("main", node("wall-2", supported_by=("base",))),
                ("main", node("wall-1", supported_by=("base",))),
            ]
        )
        state = start_cascade(graph, ["base"])

        step = advance_cascade(graph, state, tick=100, event_budget=10)

        assert [event.payload["structure_id"] for event in step.events] == [
            "base",
            "wall-1",
            "wall-2",
        ]
        assert step.events[0].event_type is EventKind.STRUCTURE_COLLAPSED
        assert step.events[0].payload["support_path"] == []
        assert step.events[1].payload["support_path"] == ["base"]
        assert step.state.done is True

    def test_budget_resumes_across_frames(self) -> None:
        graph = build_support_graph(
            [
                ("main", node("base")),
                ("main", node("b", supported_by=("base",))),
                ("main", node("a", supported_by=("base",))),
            ]
        )
        state = start_cascade(graph, ["base"])

        first = advance_cascade(graph, state, tick=100, event_budget=1)
        assert [event.payload["structure_id"] for event in first.events] == ["base"]
        second = advance_cascade(graph, first.state, tick=101, event_budget=1)
        assert [event.payload["structure_id"] for event in second.events] == ["a"]
        third = advance_cascade(graph, second.state, tick=102, event_budget=1)
        assert [event.payload["structure_id"] for event in third.events] == ["b"]
        assert third.state.done is True

        extra = advance_cascade(graph, third.state, tick=103, event_budget=1)
        assert extra.events == ()

    def test_non_active_dependents_do_not_emit(self) -> None:
        graph = build_support_graph(
            [
                ("main", node("base")),
                ("main", node("rubble", supported_by=("base",), phase=StructurePhase.RUBBLE)),
            ]
        )
        state = start_cascade(graph, ["base"])
        step = advance_cascade(graph, state, tick=1, event_budget=10)
        assert [event.payload["structure_id"] for event in step.events] == ["base"]


class TestAcceptanceScale:
    def test_10k_cascade_within_frame_budget(self) -> None:
        count = SUPPORT_GRAPH_ACCEPTANCE_NODES
        assert count == 10_000
        entries = [("main", node("s00000", load_bearing=True))]
        for index in range(1, count):
            entries.append(
                (
                    "main",
                    node(
                        f"s{index:05d}",
                        supported_by=(f"s{index - 1:05d}",),
                        load_bearing=index < count - 1,
                    ),
                )
            )
        graph = build_support_graph(entries)
        state = start_cascade(graph, ["s00000"])

        frames = 0
        emitted: list[str] = []
        while not state.done:
            step = advance_cascade(
                graph, state, tick=frames, event_budget=CASCADE_EVENT_BUDGET_PER_FRAME
            )
            assert len(step.events) <= CASCADE_EVENT_BUDGET_PER_FRAME
            emitted.extend(str(event.payload["structure_id"]) for event in step.events)
            state = step.state
            frames += 1

        assert len(emitted) == count
        assert len(set(emitted)) == count
        assert frames == count // CASCADE_EVENT_BUDGET_PER_FRAME
