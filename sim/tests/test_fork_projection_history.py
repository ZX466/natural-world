"""Invalid ancestor graphs must fail before material/structure projections write."""

from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from sim.core.persistence.fork import (
    ForkError,
    _clone_materials_at_cursor,
    _clone_structures_at_cursor,
)
from sim.core.persistence.models import Branch


@pytest.mark.parametrize(
    ("clone", "projection"),
    [(_clone_materials_at_cursor, "material"), (_clone_structures_at_cursor, "structure")],
)
@pytest.mark.parametrize("failure", ["missing", "cycle", "cutoff"])
async def test_corrupt_projection_history_rejects_without_writes(clone, projection, failure):
    branches = {}
    expected = f"missing {projection} branch history"
    if failure == "cycle":
        branches["root"] = Branch(id="root", forked_from_branch="root", forked_from_seq=1)
        expected = f"cyclic {projection} branch history"
    elif failure == "cutoff":
        branches["root"] = Branch(id="root", forked_from_branch="parent", forked_from_seq=None)
        expected = f"missing {projection} branch cutoff"

    session = AsyncMock(spec=AsyncSession)
    session.get.side_effect = lambda _model, key: branches.get(key)
    rows = Mock()
    rows.all.return_value = []
    session.scalars.return_value = rows

    with pytest.raises(ForkError, match=f"^{expected}$"):
        await clone(session, "root", 5, "child")

    session.add.assert_not_called()
    session.add_all.assert_not_called()
    session.flush.assert_not_awaited()
