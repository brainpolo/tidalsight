"""Shared agent runner with a dedicated event loop thread.

All analyst managers call LLM agents via the openai-agents library, which is
async.  Rather than calling ``asyncio.run()`` per invocation (which creates and
tears down an event loop each time and will crash if the calling thread already
has one), we maintain a single long-lived event loop on a background daemon
thread and submit coroutines to it via ``run_coroutine_threadsafe``.

This is safe to use from Celery workers regardless of their concurrency model
(prefork, threads, gevent, eventlet).
"""

import asyncio
import threading

from agents import Agent, RunConfig, Runner

from analyst.agents.provider import get_model_provider
from analyst.app_behaviour import MAX_AGENT_TURNS
from analyst.grounding import agent_grounding

_loop: asyncio.AbstractEventLoop | None = None
_lock = threading.Lock()


def _get_loop() -> asyncio.AbstractEventLoop:
    """Return (and lazily start) the shared background event loop."""
    global _loop
    if _loop is not None and _loop.is_running():
        return _loop
    with _lock:
        if _loop is not None and _loop.is_running():
            return _loop
        loop = asyncio.new_event_loop()
        thread = threading.Thread(target=loop.run_forever, daemon=True)
        thread.start()
        _loop = loop
        return _loop


def run_agent[T](agent: Agent[T], prompt: str, *, max_turns: int = MAX_AGENT_TURNS) -> T:
    """Run an openai-agents ``Agent`` synchronously and return its typed output.

    Uses a long-lived background event loop so that:
    - No event loop is created/destroyed per call.
    - It works even when the calling thread already has a running loop.
    - The loop is reused across all agent invocations in the process.
    """
    config = RunConfig(
        model_provider=get_model_provider(),
        tracing_disabled=True,
    )
    coro = Runner.run(
        agent,
        input=prompt + agent_grounding(),
        run_config=config,
        max_turns=max_turns,
    )
    future = asyncio.run_coroutine_threadsafe(coro, _get_loop())
    result = future.result()  # blocks until done
    return result.final_output
