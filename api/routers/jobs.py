import asyncio
import json
import time
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from api.services.job_manager import TERMINAL_STATUSES, job_store

router = APIRouter(prefix="/api/v1/jobs", tags=["Jobs"])

POLL_INTERVAL_SECONDS = 0.25
HEARTBEAT_SECONDS = 15


@router.get("/{job_id}")
def get_job(job_id: str):
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found or expired.")
    return job


def _sse(event: dict) -> str:
    return f"id: {event['id']}\ndata: {json.dumps(event, default=str)}\n\n"


@router.get("/{job_id}/events")
async def stream_job_events(
    job_id: str,
    request: Request,
    last_event_id: Optional[str] = Header(None, alias="Last-Event-ID"),
    after: int = Query(0, ge=0),
):
    """Server-Sent Events for one job.

    Replays everything after ``Last-Event-ID`` (sent automatically by
    EventSource on reconnect) or ``?after=``, then streams live events until
    the job completes or fails.
    """
    if job_store.get(job_id) is None:
        raise HTTPException(status_code=404, detail="Job not found or expired.")

    try:
        cursor = int(last_event_id) if last_event_id else after
    except ValueError:
        cursor = after

    async def event_stream():
        nonlocal cursor
        # Tell EventSource how long to wait before reconnecting.
        yield "retry: 2000\n\n"
        last_sent = time.monotonic()

        while True:
            if await request.is_disconnected():
                return

            events = job_store.events_since(job_id, cursor)
            if events is None:
                return

            for event in events:
                cursor = event["id"]
                yield _sse(event)
                last_sent = time.monotonic()

            job = job_store.get(job_id)
            if job is None or (job["status"] in TERMINAL_STATUSES and cursor >= job["last_event_id"]):
                return

            if time.monotonic() - last_sent > HEARTBEAT_SECONDS:
                yield ": keep-alive\n\n"
                last_sent = time.monotonic()

            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Disable proxy buffering (nginx) so events arrive immediately.
            "X-Accel-Buffering": "no",
        },
    )
