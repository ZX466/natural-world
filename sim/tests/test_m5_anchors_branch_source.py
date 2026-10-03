"""M5-A6 R-4 施工数据面钉 — anchors 记档游标必须走 `branches` 真源（先红后绿）

**背景**：缺陷 R-4（codex S4）= `sim/api/anchors.py` 两处硬编码 `'main'`——
`:274` 取 seq 的 SQL、`:345` 建档的 `branch_id`。分叉后它们指向**被弃时间线**，
记档三元组 `(branch_id, tick, seq)` 自相矛盾。数据面已就位（A5：0012 `is_current` +
部分唯一索引 + `SqlEventStore.current_branch_id()`），本文件把「施工必须满足的接缝」
写成钉子：**生产文件 `sim/api/anchors.py` 本单零改动**（那是 Claude 的施工面）。

## 先红后绿口径 = **skip-locked**（不是预期红），理由与解锁条件

施工前这些钉若是红的，`-m "not bench"` 门禁立刻假红，收编方分不清「新缺陷」与「已知待施工」。
故选用 skip-lock：

- **锁信号** = `anchors.py` 的**代码**里出现真源载体（调用 `current_branch_id` **或**
  直接查 `is_current`）。两种实现都认 ⇒ 施工换个写法也不会让钉永久沉睡。
- **解锁时机** = 施工合入后，pytest 重新收集本文件即自动转绿，无需人工摘标记。
- **反假绿灯**：锁信号与红线必须同向（`test_lock_signal_agrees_with_redline`）。
  删掉硬编码却不接真源 ⇒ 信号说「已接」而红线说「无字面量」⇒ 该钉立刻红，
  而不是让整组钉安静沉睡。

## 三组钉的分工（组名 = 类名前缀）：

- **skip-locked**（施工后转绿）：`TestRedLineNoMainLiteral`（代码无 `'main'` 字面量）、
  `TestCursorTripleCoherence`（真源≠'main' 时 `(branch_id, seq)` 同源自洽）、
  `TestFailClosed`（无当前行 / ≥2 active ⇒ 拒绝且不落行）。
- **今天即绿**（数据面已就位）：`TestGateAndTrueSource`（启动开的线即当前行；
  读档子线可 append 且不抢当前行；真源恰为 'main' 的正控）、
  `TestForkHandoverForm`（fork 两模式的「至多一个当前」不变量，守卫口径稿）。

⚠️ **判别力说明**：真源恰好是 `'main'` 的用例**判别力弱**（今天的硬编码恰好也对）。
它只作正控（证明施工没把正常路径一起拒掉）；真正的判别力由「真源≠'main'」那组承担——
本文件所有涉 `POST` 的钉都把两条线的头部 seq 故意设成**不同值**（child=7 / main=3），
于是「只改一处」必然被抓：只改取 seq ⇒ branch 仍 'main'；只改建档 ⇒ seq 来自 main 头部。

环境纪律（沿用 A5）：夹具 `monkeypatch.chdir(tmp_path)`——app 的 store 与 `AnchorStore`
都指向**同一个** `world.db`（相对 CWD ⇒ 落临时库，生产形态），**绝不碰仓根 `world.db`**。
"""

from __future__ import annotations

import ast
import asyncio
import contextlib
import io
import time
import tokenize
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from sim.api import anchors as anchors_mod
from sim.api.ws import reset_anchor_registry
from sim.core.persistence.fork import fork_from_anchor
from sim.core.persistence.models import Base, Branch, Event, PlayerAnchor

#: 施工面文件（本单只读、不改）。
ANCHORS_PY = Path(__file__).resolve().parents[1] / "api" / "anchors.py"

#: 两条线的头部刻意不同（child 7 / main 3）⇒「只改一处」必被抓（见模块 docstring）。
CHILD, CHILD_HEAD = "fork-1", 7
MAIN, MAIN_HEAD = "main", 3


# ---------------------------------------------------------------------------
# 施工面静态探针（红线 + 锁信号）
# ---------------------------------------------------------------------------


def _anchors_src() -> str:
    return ANCHORS_PY.read_text(encoding="utf-8")


def _docstring_lines(src: str) -> set[int]:
    """docstring 覆盖的行号集合（红线扫描要放过它们：口径说明里允许提 'main'）。"""
    lines: set[int] = set()
    for node in ast.walk(ast.parse(src)):
        if not isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            lines.update(range(first.lineno, (first.end_lineno or first.lineno) + 1))
    return lines


def _main_literals(src: str) -> list[int]:
    """代码里出现 `'main'` 的行号（docstring 除外；SQL 串里含 main 也算）。"""
    skip = _docstring_lines(src)
    hits: list[int] = []
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type != tokenize.STRING or tok.start[0] in skip:
            continue
        try:
            value = ast.literal_eval(tok.string)
        except (ValueError, SyntaxError):
            continue
        if isinstance(value, str) and "main" in value:
            hits.append(tok.start[0])
    return hits


def _true_source_landed() -> bool:
    """R-4 施工是否已落：代码里出现真源载体（两种实现都认）。

    ⚠️ 已知局限：f-string 的插值会整体落进 STRING token 而被排除——本仓的 SQL 是
    普通字符串字面量，不受影响；若施工把真源拼进 f-string，本锁可能延迟解锁，
    此时红线钉会先红（假红可接受，假绿不可接受）。
    """
    src = _anchors_src()
    skip = _docstring_lines(src)
    code = "\n".join(line for lineno, line in enumerate(src.splitlines(), 1) if lineno not in skip)
    return "current_branch_id" in code or "is_current" in code


requires_r4_construction = pytest.mark.skipif(
    not _true_source_landed(),
    reason="R-4 施工单未落（anchors.py 游标/建档未接 branches 真源）——施工合入后自动解锁",
)


# ---------------------------------------------------------------------------
# 夹具与工具
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_anchor_registry() -> Iterator[None]:
    reset_anchor_registry()
    yield
    reset_anchor_registry()


@pytest.fixture()
def world_db(tmp_path, monkeypatch) -> Path:
    """app 的 event store 与 `AnchorStore` 指向**同一** DB 文件（生产形态）。

    app 的库名是相对 CWD 的 `world.db` ⇒ chdir 到 tmp_path，**顺带保证本文件不碰
    仓根 `world.db`**（A4 血的教训：那是开发库，版本行还会说谎）。
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LZ_MASTER_KEY", "t" * 44)
    from sim.api.settings import get_profile_store

    get_profile_store().__init__(f"sqlite:///{tmp_path / 'settings.db'}")
    anchors_mod.get_anchor_store().__init__(f"sqlite:///{tmp_path / 'world.db'}")
    return tmp_path / "world.db"


@contextlib.contextmanager
def _app() -> Iterator[TestClient]:
    from sim.api.main import app

    with TestClient(app) as client:
        yield client


@contextlib.contextmanager
def _seeded_app(db: Path, spec: Sequence[tuple[str, int, bool, str]]) -> Iterator[TestClient]:
    """先种世界态再起 app（顺序重要：起 app 后 driver 会往 'main' 追加事件）。"""
    _seed_world(db, spec)
    with _app() as client:
        yield client


def _seed_world(db: Path, spec: Sequence[tuple[str, int, bool, str]]) -> None:
    """种世界态：`spec` 每项 = `(branch_id, head_seq, is_current, status)`。"""
    engine = create_engine(f"sqlite:///{db}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        for branch_id, head, is_current, status in spec:
            session.add(Branch(id=branch_id, status=status, is_current=is_current))
            for seq in range(1, head + 1):
                session.add(
                    Event(
                        branch_id=branch_id,
                        seq=seq,
                        tick=seq,
                        event_type="npc.lod_change",
                        actor_id="",
                        payload="{}",
                        witnesses="[]",
                    )
                )
        session.commit()
    engine.dispose()


def _query(db: Path, sql: str) -> Sequence[Sequence[Any]]:
    engine = create_engine(f"sqlite:///{db}")
    try:
        with Session(engine) as session:
            return [tuple(r) for r in session.execute(sa_text(sql))]
    finally:
        engine.dispose()


def _branch_flags(db: Path) -> dict[str, bool]:
    return {str(r[0]): bool(r[1]) for r in _query(db, "SELECT id, is_current FROM branches")}


def _branch_state(db: Path) -> dict[str, tuple[bool, str]]:
    return {
        str(r[0]): (bool(r[1]), str(r[2]))
        for r in _query(db, "SELECT id, is_current, status FROM branches")
    }


#: 交接施工面（本单只读、不改）：`fork.py` 里当前行的移交归 R-4 施工单。
FORK_PY = Path(__file__).resolve().parents[1] / "core" / "persistence" / "fork.py"

#: 0012 迁移（只读）：头注须留「本迁移不移动当前行」+ 双态钉指针。
M0012_PY = (
    Path(__file__).resolve().parents[1]
    / "core"
    / "persistence"
    / "alembic"
    / "versions"
    / "0012_branches_current.py"
)


def _handover_landed() -> bool:
    """交接是否已落：``fork.py`` 的**代码**里出现 ``is_current``（本单选定的锁信号）。

    口径与理由：只扫**代码**（跳过注释与 docstring），因为 ``fork.py`` 的口径说明需要
    反复谈「当前行」而那些字样不是实现；留下的是真正的读写载体（``UPDATE … SET
    is_current`` / ``.values(is_current=…)`` / 查询）。今日 ``fork.py`` 代码里该记号
    **零出现** ⇒ 信号为假，本组钉停在「交接前现状」态；R-4 施工合入后自动转「交接后」态。
    """
    src = FORK_PY.read_text(encoding="utf-8")
    skip = _docstring_lines(src)
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.COMMENT:
            skip.add(tok.start[0])
    code = "\n".join(line for lineno, line in enumerate(src.splitlines(), 1) if lineno not in skip)
    return "is_current" in code


def _head_seq(db: Path, branch_id: str) -> int:
    rows = _query(db, f"SELECT COALESCE(MAX(seq), 0) FROM events WHERE branch_id = '{branch_id}'")
    return int(rows[0][0])


def _anchors(db: Path) -> list[PlayerAnchor]:
    engine = create_engine(f"sqlite:///{db}")
    try:
        with Session(engine) as session:
            return list(session.query(PlayerAnchor).order_by(PlayerAnchor.created_at).all())
    finally:
        engine.dispose()


def _await_until(predicate: Callable[[], bool], timeout: float = 10.0) -> bool:
    """轮询等待（driver 首帧 flush 是异步任务，起 app 后立刻断言会有竞态）。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


def _fork_now(db: Path, *, parent: str, fork_seq: int, fork_tick: int, child: str) -> None:
    """在测试进程里跑一次 fork（独立事件循环，不依赖 app 的 loop）。"""

    async def _run() -> None:
        engine = create_async_engine(f"sqlite+aiosqlite:///{db}")
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async def _preflush() -> None:
            return None

        try:
            await fork_from_anchor(
                factory,
                parent_branch_id=parent,
                fork_seq=fork_seq,
                fork_tick=fork_tick,
                new_branch_id=child,
                preflush=_preflush,
            )
        finally:
            await engine.dispose()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 1. 红线：代码里不再有 'main' 字面量（施工后转绿）
# ---------------------------------------------------------------------------


@requires_r4_construction
class TestRedLineNoMainLiteral:
    def test_no_main_literal_in_code(self) -> None:
        """`:274`/`:345` 的 `'main'` 必须消失（含 SQL 串里的）。

        R-4.1：真源是 `branches` 表，**禁** `'main'` 之类字面量兜底——猜分支 =
        记档指向错误世界线，比拒绝更坏。docstring 里的历史口径说明不算（可读性豁免）。
        """
        hits = _main_literals(_anchors_src())
        assert hits == [], f"anchors.py 代码里仍有 'main' 字面量（行 {hits}）——游标/建档必须走真源"

    def test_lock_signal_agrees_with_redline(self) -> None:
        """锁信号与红线同向：真源已接 ⇒ 代码里就不该再有 'main'。

        防「锁假开」：删掉硬编码却不接真源（游标恒 0 或直接崩）时本钉立刻红，
        而不是让整组施工钉静默沉睡成假绿灯。
        """
        landed = _true_source_landed()
        violations = _main_literals(_anchors_src())
        assert landed == (not violations), (
            f"锁信号 {landed} 与红线 {violations} 不同向：真源载体缺失但字面量也没了"
            "（或反之）——施工只做了一半"
        )


# ---------------------------------------------------------------------------
# 2. 游标三元组自洽：真源 ≠ 'main'（施工后转绿）
# ---------------------------------------------------------------------------


@requires_r4_construction
class TestCursorTripleCoherence:
    def test_post_branch_and_seq_come_from_true_source(self, world_db: Path) -> None:
        """真源 = 'fork-1'（头部 7）时，POST 记档的 `branch_id`/`seq` 必须同出该线。

        判别力：'main' 头部 3 ≠ 7 ⇒ **只改一处必被抓**（只改取 seq ⇒ branch 仍
        'main'；只改建档 ⇒ seq 来自 main 的头部）。这才是 A4「同改警告」的可证伪版。
        """
        spec = [(CHILD, CHILD_HEAD, True, "active"), (MAIN, MAIN_HEAD, False, "active")]
        with _seeded_app(world_db, spec) as client:
            r = client.post("/api/anchors", json={"name": "溪畔回声"})
            assert r.status_code == 201, r.text
            item = _anchors(world_db)[-1]
            assert item.branch_id == CHILD, "档的 branch 指向错误世界线（R-4）"
            assert item.seq == CHILD_HEAD, "seq 来自另一条线 ⇒ 三元组自相矛盾"

    def test_post_does_not_move_current_line(self, world_db: Path) -> None:
        """记档对当前行**只读**，不得顺手改 `is_current`（否则记一次档就换线）。"""
        spec = [(CHILD, CHILD_HEAD, True, "active"), (MAIN, MAIN_HEAD, False, "active")]
        with _seeded_app(world_db, spec) as client:
            before = _branch_flags(world_db)
            client.post("/api/anchors", json={"name": "溪畔低语"})
            assert _branch_flags(world_db) == before


# ---------------------------------------------------------------------------
# 3. fail-closed：无当前行 / 歧义库（施工后转绿）
# ---------------------------------------------------------------------------


@requires_r4_construction
class TestFailClosed:
    def test_post_without_current_row_fails_closed(self, world_db: Path) -> None:
        """无当前行 ⇒ 拒绝（≥400），**且不落任何档行**——绝不回退 'main'。

        状态码不断言具体值（kilo 契约里 409/503 都可），只断言「拒绝 + 零落行」。
        """
        with _seeded_app(world_db, [(MAIN, MAIN_HEAD, False, "active")]) as client:
            r = client.post("/api/anchors", json={"name": "无当前线"})
            assert r.status_code >= 400, "无当前世界线却记档成功 = 猜了分支（R-4.1）"
            assert _anchors(world_db) == [], "被拒的记档仍落了行"

    def test_post_with_ambiguous_active_rows_fails_closed(self, world_db: Path) -> None:
        """两条 active 但无当前行（0012 回填后的歧义库）⇒ 拒绝，**不 recency 兜底**。

        recency 兜底会把「玩家在跑的线」换成「最近被分叉出去的线」，且**静默错**。
        """
        with _seeded_app(world_db, [("a1", 2, False, "active"), ("a2", 5, False, "active")]) as c:
            r = c.post("/api/anchors", json={"name": "歧义库"})
            assert r.status_code >= 400, "世界线状态歧义却记档成功"
            assert _anchors(world_db) == []


# ---------------------------------------------------------------------------
# 4. 开线闸 ↔ 真源（**今天即绿**：数据面已就位）
# ---------------------------------------------------------------------------


class TestGateAndTrueSource:
    def test_startup_opens_line_and_marks_current(self, world_db: Path) -> None:
        """app 启动开的那条线必须**同时**是当前行（开线闸 = 真源行的产生口）。

        闸门（`store.py::_assert_branch_writable`）开线时写 `is_current=1`，于是
        「driver 顺手开的线」与「记档要用的真源」天然同一条——这条缝一断（闸门开了线
        却没置真 / 真源指向别的行），记档会在启动后立刻失去世界线。
        """
        with _app() as client:
            assert _await_until(lambda: _head_seq(world_db, MAIN) > 0), "启动后 driver 没落事件"
            assert _branch_flags(world_db).get(MAIN) is True, "开线未置当前行"
            assert client.get("/api/anchors").status_code == 200

    def test_archive_line_appendable_and_current_untouched(self, world_db: Path) -> None:
        """读档子线（active + 非当前）**照写不误**，且写入不抢当前行。

        这是 0012 闸门收紧最容易被误伤的一格：若收紧成「非当前不可写」，历史点读档线
        会被写死。判别力：等 driver 真的往 'main' 落一条事件（落不下 ⇒ 闸门收过头）。
        """
        spec = [(CHILD, CHILD_HEAD, True, "active"), (MAIN, MAIN_HEAD, False, "active")]
        with _seeded_app(world_db, spec) as client:
            assert _await_until(lambda: _head_seq(world_db, MAIN) > MAIN_HEAD), (
                "读档子线写不进去（闸门误伤非当前分支）"
            )
            assert _branch_flags(world_db)[CHILD] is True, "读档子线的写入抢走了当前行"
            assert client.get("/api/anchors").status_code == 200

    def test_positive_control_post_on_opened_line(self, world_db: Path) -> None:
        """正控：真源恰好是 'main'（闸门开的那条）时记档行为不变。

        判别力弱（今天的硬编码恰好也对），只防施工把**正常路径**一起拒掉。
        """
        with _app() as client:
            assert _await_until(lambda: _head_seq(world_db, MAIN) > 0)
            r = client.post("/api/anchors", json={"name": "正控档"})
            assert r.status_code == 201, r.text
            item = _anchors(world_db)[-1]
            assert item.branch_id == MAIN
            assert 0 <= item.seq <= _head_seq(world_db, MAIN)


# ---------------------------------------------------------------------------
# 5. fork 交接形态的不变量（**今天即绿**，口径稿的守卫）
#    口径：docs/data/m5-fork-current-handover.md
# ---------------------------------------------------------------------------


class TestForkHandoverForm:
    def test_fork_from_current_line_keeps_single_current(self, world_db: Path) -> None:
        """从当前线分叉后：当前行**唯一**，且归属按 `fork.py` 交接施工落否**双态**。

        - **不变量（与时序无关）**：分叉后至多一条当前行（部分唯一索引 `ux_branches_current`
          兜底）——这是本钉的硬判据，任何形态下都必须成立。
        - **锁信号（本单选定，写明）**：`sim/core/persistence/fork.py` 的**代码**里出现
          ``is_current`` 记号（跳过注释与 docstring；赋值 / UPDATE SET / 查询皆算）即视为
          「交接已落」。选它的理由：`is_current` 今日在 `fork.py` 的代码里**零出现**，
          所以它是单一、可 grep、且不随实现写法（``.values(...)`` / 裸 SQL）漂移的信号；
          只扫代码则让 `fork.py` 的口径说明可以照常谈「当前行」而不误触信号。
        - **双态**：交接未落 ⇒「父仍持当前位 + 子非当前」（0012 时现状）；交接已落 ⇒
          「子当前 + 父 `abandoned`」。两态都绿 ⇒ 施工合入前后本文件都不假红。

        ⚠️ 反假绿灯：态 A 的断言在交接落地后会**主动变红**（不是被 skip 掉），所以「施工
        落地却仍按旧态记账」这种假绿不可能发生。
        """
        _seed_world(world_db, [(MAIN, MAIN_HEAD, True, "active")])
        _fork_now(world_db, parent=MAIN, fork_seq=MAIN_HEAD, fork_tick=MAIN_HEAD, child=CHILD)
        state = _branch_state(world_db)
        flags = {bid: cur for bid, (cur, _st) in state.items()}
        assert sum(flags.values()) <= 1, f"分叉后出现两个当前世界线：{flags}"

        landed = _handover_landed()
        if landed:
            assert flags[CHILD] is True and flags[MAIN] is False, (
                f"交接已落（fork.py 出现 is_current）却仍是旧归属：{state}"
            )
            assert state[MAIN][1] == "abandoned", (
                f"交接已落但父未封存（子当前 + 父 abandoned 是交接后语义）：{state}"
            )
        else:
            assert flags[MAIN] is True and flags[CHILD] is False, (
                f"交接未落（fork.py 零 is_current）却已交出当前行：{state}"
            )

    def test_handover_dual_state_is_exhausted(self, world_db: Path) -> None:
        """双态判据**穷尽**：分叉后当前行只能是父或子之一，且子行必存在。

        判别力：若某天施工把当前行「复制」给子行（本该由唯一索引拦），或子行没建出来，
        这里会先于具体归属断言报错——双态白名单外的第三种形态没有藏身处。
        """
        _seed_world(world_db, [(MAIN, MAIN_HEAD, True, "active")])
        _fork_now(world_db, parent=MAIN, fork_seq=MAIN_HEAD, fork_tick=MAIN_HEAD, child=CHILD)
        state = _branch_state(world_db)
        assert CHILD in state, f"子分支行没建出来：{state}"
        holders = [bid for bid, (cur, _st) in state.items() if cur]
        assert holders in ([MAIN], [CHILD]), f"当前行归属落在双态白名单之外：{state}"

    def test_0012_docstring_points_at_handover_unit(self) -> None:
        """0012 迁移头注必须指着交接施工单 + 预置钉（本 G3 小单的零生产码契约）。

        判别力：这段头注是「0012 只提供载体、交接归 R-4 施工单」的唯一书面线索；
        少了它，后来者会把「当前行移交」当成 0012 的欠账去改迁移 ⇒ 本钉红。
        **双态**：交接未落 ⇒ 头注必须仍是「交接待施工」口径（未落标记）；
        交接已落 ⇒ 头注必须补「交接已落」注记（否则后来者仍当欠账）。
        """
        src = M0012_PY.read_text(encoding="utf-8")
        assert "本迁移不移动当前行" in src, "0012 头注丢了「本迁移不移动当前行」的声明"
        pointer = [line for line in src.splitlines() if "TestForkHandoverForm" in line]
        assert pointer, "0012 头注没有指向双态钉（TestForkHandoverForm）"
        assert "R-4" in src and "fork.py" in src, "0012 头注没写明交接归属 fork.py / R-4"
        if _handover_landed():
            assert "交接已落" in src, (
                "fork.py 已实现交接，但 0012 头注没有「交接已落」注记"
                "——后来者会把交接当成 0012 的欠账"
            )
        else:
            assert "交接已落" not in src, (
                "交接未落但 0012 头注已写「交接已落」=假记账"
            )

    def test_fork_from_archive_line_keeps_true_source(self, world_db: Path) -> None:
        """从**读档线**分叉：不碰当前行（子只是又一条并存线）。

        口径稿的核心分支：交接只在「父就是当前行」时发生；从非当前线分叉若也去抢
        当前行，玩家正在跑的线会被一次读档悄悄换掉。
        """
        spec = [(CHILD, CHILD_HEAD, True, "active"), (MAIN, MAIN_HEAD, False, "active")]
        _seed_world(world_db, spec)
        _fork_now(
            world_db, parent=MAIN, fork_seq=MAIN_HEAD, fork_tick=MAIN_HEAD, child="fork-archive"
        )
        flags = _branch_flags(world_db)
        assert flags[CHILD] is True, "读档线分叉抢走了当前行"
        assert flags["fork-archive"] is False, "子线被错置为当前行"
