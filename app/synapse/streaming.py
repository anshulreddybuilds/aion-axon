"""Server-Sent Events streaming wrapper around synapse.propose().

The existing `synapse.propose()` runs the full pipeline synchronously in
one blocking call, which is correct for governance (one atomic record) but
opaque to a watching human: the browser shows a spinner for 10-30s and
then a wall of text appears.

This module wraps propose() so the frontend can subscribe to a stream and
see each stage arrive as it happens:

    GUARDIAN_PRESCREEN → RESEARCH → GENERATE → SAFETY_SCREEN →
    SANDBOX_TEST → EVALUATE → GUARDIAN_SCREEN → AWAITING_APPROVAL

It does this by running propose() in a background thread and using Python's
built-in `queue.Queue` as a thread-safe channel between the worker thread
and the SSE generator coroutine in the main event loop.

Stage events are emitted by a lightweight `_StageTracker` that wraps the
`AcquisitionRecord` object and intercepts stage/status writes. This does
NOT change the engine itself -- the engine and its tests are unmodified.

Every event is a JSON object:
    {"type": "stage", "stage": "<STAGE_NAME>", "status": "ACTIVE", ...}
    {"type": "stage", "stage": "<STAGE_NAME>", "status": "DONE", "detail": "..."}
    {"type": "done",  "record": { <full terminal AcquisitionRecord.to_dict()> }}
    {"type": "error", "message": "..."}

The `record` in the `done` event is identical to what the synchronous
POST /synapse/propose would return -- no data is fabricated.
"""
import json
import queue
import threading
from typing import Any, Generator, Optional

from app.synapse.engine import AcquisitionRecord, SynapseEngine

_SENTINEL = object()  # signals end-of-stream


class _TrackedRecord(AcquisitionRecord):
    """AcquisitionRecord subclass that emits queue events on stage changes.

    Only `stage` and `status` are intercepted — every other attribute
    behaves identically to the base class, so the engine doesn't know
    it's talking to a wrapper.
    """

    def __init__(self, event_queue: "queue.Queue[Any]", **kwargs):
        # Use object.__setattr__ to bypass our own __setattr__ during init
        object.__setattr__(self, "_event_queue", event_queue)
        object.__setattr__(self, "_current_stage", None)
        super().__init__(**kwargs)

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "stage" and value != object.__getattribute__(self, "_current_stage"):
            q = object.__getattribute__(self, "_event_queue")
            # Complete the previous stage
            prev = object.__getattribute__(self, "_current_stage")
            if prev is not None:
                q.put({"type": "stage", "stage": prev, "status": "DONE"})
            # Announce the new stage as ACTIVE
            q.put({"type": "stage", "stage": value, "status": "ACTIVE"})
            object.__setattr__(self, "_current_stage", value)
        super().__setattr__(name, value)


class _StreamingEngine(SynapseEngine):
    """SynapseEngine that uses _TrackedRecord instead of AcquisitionRecord.

    The only override is the one line in propose() that creates the record.
    Everything else -- kill switch, guardian, research, generate, screen,
    sandbox, evaluate, approval -- runs identically.
    """

    def __init__(self, event_queue: "queue.Queue[Any]"):
        self._event_queue = event_queue

    def propose(
        self,
        need: str,
        mission_id: Optional[str] = None,
        allow_retry: bool = False,
    ) -> AcquisitionRecord:
        # Patch: create a _TrackedRecord instead of AcquisitionRecord.
        # We do this by temporarily replacing the class reference in the
        # engine's local scope. Since SynapseEngine.propose() calls
        # AcquisitionRecord() by name from the class's own module, the
        # cleanest override is to monkeypatch it in for this call only.
        import app.synapse.engine as engine_mod
        original = engine_mod.AcquisitionRecord
        engine_mod.AcquisitionRecord = lambda **kw: _TrackedRecord(
            event_queue=self._event_queue, **kw
        )
        try:
            return super().propose(need, mission_id, allow_retry=allow_retry)
        finally:
            engine_mod.AcquisitionRecord = original


def stream_propose(
    need: str,
    mission_id: Optional[str],
    allow_retry: bool,
    owner_token: Optional[str],
) -> Generator[str, None, None]:
    """Generator that yields SSE-formatted strings for an acquisition run.

    Called from an async FastAPI route via `StreamingResponse`. Each
    `yield` is one SSE message. The generator finishes when the engine
    thread completes (sentinel received) or produces an error.

    SSE format:
        data: <json>\n\n
    """
    q: queue.Queue[Any] = queue.Queue()
    engine = _StreamingEngine(q)

    def _worker():
        try:
            record = engine.propose(need, mission_id, allow_retry=allow_retry)
            # Finalize the last stage
            if record.stage:
                q.put({"type": "stage", "stage": record.stage, "status": "DONE",
                       "detail": record.reason or record.status})
            q.put({"type": "done", "record": record.to_dict()})
        except Exception as exc:  # noqa: BLE001
            q.put({"type": "error", "message": str(exc)})
        finally:
            q.put(_SENTINEL)

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()

    # Yield a heartbeat immediately so the browser knows the connection
    # is alive before the engine starts.
    yield f"data: {json.dumps({'type': 'connected'})}\n\n"

    while True:
        try:
            event = q.get(timeout=120)  # 120s max -- longer than any real run
        except queue.Empty:
            yield f"data: {json.dumps({'type': 'error', 'message': 'stream timeout'})}\n\n"
            break

        if event is _SENTINEL:
            break

        yield f"data: {json.dumps(event)}\n\n"

    thread.join(timeout=5)
