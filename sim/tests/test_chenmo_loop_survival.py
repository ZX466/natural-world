"""A bad prompt or transient decision failure must not kill the live task."""

import asyncio
from unittest.mock import Mock

import pytest

from sim.agent.driver import ChenmoDriver
from sim.api import main
from sim.llm.prompts.assembler import PromptAssemblyError


@pytest.mark.parametrize(
    "failure", [PromptAssemblyError(("bad-test-word",)), RuntimeError("temporary")]
)
async def test_live_loop_survives_failed_decision_and_keeps_cancellation(monkeypatch, failure):
    first = asyncio.Event()
    recovered = asyncio.Event()
    calls = 0
    log = Mock()
    monkeypatch.setattr(main, "logger", log)

    async def held_world_driver(*args, **kwargs):
        await asyncio.Event().wait()

    async def flaky_decide(driver, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            driver.request_decision()
            first.set()
            raise failure
        recovered.set()
        return False

    monkeypatch.setattr(main, "run_world_driver", held_world_driver)
    monkeypatch.setattr(ChenmoDriver, "decide_once", flaky_decide)
    async with main.lifespan(main.app):
        main.app.state.chenmo_driver.request_decision()
        await asyncio.wait_for(first.wait(), 3)
        await asyncio.sleep(0)
        task = main.app.state.chenmo_task
        assert not task.done(), "A single decision exception killed Chenmo's task"
        await asyncio.wait_for(recovered.wait(), 3)
        assert calls >= 2
        assert log.exception.call_count == 1
        assert log.exception.call_args.args[0] == "chenmo.decision_failed"
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
