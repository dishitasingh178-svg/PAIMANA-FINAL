"""Background job tracking for long-running pipelines (PDF ingestion today).

Every job owns its own state and an append-only event log. Producers (the
pipeline, running in a worker thread) call ``JobReporter`` methods; consumers
(the SSE endpoint) read events after a sequence number. Nothing here is global
per-upload state, so concurrent uploads never interfere with each other.

The in-memory store is enough for a single uvicorn process. To scale out,
implement ``JobStore`` on Redis (a hash per job + a stream per event log, with
XREAD replacing ``events_since``) and swap ``job_store`` below; the pipeline
and the SSE router only depend on this interface.
"""

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from typing import Any, Callable, Dict, List, Optional


# Lifecycle
QUEUED = "queued"
RUNNING = "running"
COMPLETED = "completed"
FAILED = "failed"
TERMINAL_STATUSES = {COMPLETED, FAILED}

# Per-stage status
STAGE_PENDING = "pending"
STAGE_RUNNING = "running"
STAGE_DONE = "done"
STAGE_SKIPPED = "skipped"
STAGE_FAILED = "failed"

# Stages of the PDF pipeline, in order, with their share of overall progress.
PDF_STAGES = [
    ("received", "PDF received", 2),
    ("validating", "Validating document", 5),
    ("extracting", "PDF extraction", 30),
    ("normalizing", "Data normalization", 5),
    ("ingesting", "Database ingestion", 18),
    ("predicting", "ML predictions", 30),
    ("alerting", "Early-warning generation", 5),
    ("complete", "Processing complete", 5),
]

JOB_TTL_SECONDS = 60 * 60
MAX_JOBS = 200


def _now() -> float:
    return time.time()


class Job:
    def __init__(self, job_id: str, kind: str, stages, metadata: Dict[str, Any]):
        self.job_id = job_id
        self.kind = kind
        self.status = QUEUED
        self.stage: Optional[str] = None
        self.progress = 0.0
        self.message = "Queued"
        self.error: Optional[str] = None
        self.result: Optional[Dict[str, Any]] = None
        self.metadata = metadata
        self.counters: Dict[str, Any] = {}
        self.created_at = _now()
        self.updated_at = self.created_at
        self.finished_at: Optional[float] = None
        self.stage_weights = {key: weight for key, _, weight in stages}
        self.stages: Dict[str, Dict[str, Any]] = {
            key: {
                "key": key,
                "label": label,
                "status": STAGE_PENDING,
                "progress": 0.0,
                "message": None,
                "details": [],
            }
            for key, label, _ in stages
        }
        self.events: List[Dict[str, Any]] = []

    def overall_progress(self) -> float:
        total = sum(self.stage_weights.values()) or 1
        done = 0.0
        for key, stage in self.stages.items():
            weight = self.stage_weights.get(key, 0)
            if stage["status"] in (STAGE_DONE, STAGE_SKIPPED):
                done += weight
            elif stage["status"] == STAGE_RUNNING:
                done += weight * stage["progress"]
        return round(100.0 * done / total, 1)

    def snapshot(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "kind": self.kind,
            "status": self.status,
            "stage": self.stage,
            "progress": self.progress,
            "message": self.message,
            "error": self.error,
            "result": self.result,
            "metadata": self.metadata,
            "counters": self.counters,
            "stages": list(self.stages.values()),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "finished_at": self.finished_at,
            "last_event_id": len(self.events),
        }


class JobStore:
    """Interface for job persistence. See module docstring."""

    def create(self, kind: str, stages, metadata: Optional[Dict[str, Any]] = None) -> str:
        raise NotImplementedError

    def get(self, job_id: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def apply(self, job_id: str, event: Dict[str, Any]) -> None:
        raise NotImplementedError

    def events_since(self, job_id: str, after: int) -> Optional[List[Dict[str, Any]]]:
        raise NotImplementedError


class InMemoryJobStore(JobStore):
    def __init__(self):
        self._jobs: Dict[str, Job] = {}
        self._lock = threading.Lock()

    def _evict(self) -> None:
        cutoff = _now() - JOB_TTL_SECONDS
        expired = [
            job_id for job_id, job in self._jobs.items()
            if job.finished_at and job.finished_at < cutoff
        ]
        for job_id in expired:
            del self._jobs[job_id]

        if len(self._jobs) > MAX_JOBS:
            finished = sorted(
                (job for job in self._jobs.values() if job.finished_at),
                key=lambda job: job.finished_at,
            )
            for job in finished[: len(self._jobs) - MAX_JOBS]:
                del self._jobs[job.job_id]

    def create(self, kind, stages, metadata=None):
        job_id = uuid.uuid4().hex
        with self._lock:
            self._evict()
            self._jobs[job_id] = Job(job_id, kind, stages, dict(metadata or {}))
        return job_id

    def get(self, job_id):
        with self._lock:
            job = self._jobs.get(job_id)
            return deepcopy(job.snapshot()) if job else None

    def apply(self, job_id, event):
        with self._lock:
            job = self._jobs.get(job_id)
            # A timed-out extraction thread may keep reporting after the job
            # has failed; drop anything that arrives after a terminal state.
            if job is None or job.status in TERMINAL_STATUSES:
                return

            stage_key = event.get("stage")
            stage = job.stages.get(stage_key) if stage_key else None

            if stage is not None:
                if event.get("stage_status"):
                    stage["status"] = event["stage_status"]
                    if event["stage_status"] in (STAGE_DONE, STAGE_SKIPPED):
                        stage["progress"] = 1.0
                if event.get("stage_progress") is not None:
                    stage["progress"] = max(0.0, min(1.0, float(event["stage_progress"])))
                if event.get("message"):
                    stage["message"] = event["message"]
                if event.get("detail"):
                    stage["details"].append(event["detail"])
                if stage["status"] == STAGE_RUNNING:
                    job.stage = stage_key

            if event.get("counters"):
                job.counters.update(event["counters"])
            if event.get("message"):
                job.message = event["message"]

            if event["type"] == "job_started":
                job.status = RUNNING
            elif event["type"] == "job_completed":
                job.status = COMPLETED
                job.result = event.get("result")
                job.finished_at = _now()
            elif event["type"] == "job_failed":
                job.status = FAILED
                job.error = event.get("error")
                job.finished_at = _now()
                if job.stage and job.stages[job.stage]["status"] == STAGE_RUNNING:
                    job.stages[job.stage]["status"] = STAGE_FAILED

            job.progress = 100.0 if job.status == COMPLETED else job.overall_progress()
            job.updated_at = _now()

            event = dict(event)
            event["id"] = len(job.events) + 1
            event["job_id"] = job_id
            event["status"] = job.status
            event["progress"] = job.progress
            event["timestamp"] = job.updated_at
            job.events.append(event)

    def events_since(self, job_id, after):
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            return deepcopy(job.events[max(0, after):])


class JobReporter:
    """What a pipeline uses to publish progress for one job."""

    def __init__(self, store: JobStore, job_id: str):
        self.store = store
        self.job_id = job_id
        self._tag = job_id[:8]

    def _emit(self, event_type: str, **fields) -> None:
        event = {"type": event_type}
        event.update({k: v for k, v in fields.items() if v is not None})
        self.store.apply(self.job_id, event)

    def started(self, message: str = "Processing started") -> None:
        print(f"[JOB {self._tag}] started", flush=True)
        self._emit("job_started", message=message)

    def stage_started(self, stage: str, message: str) -> None:
        print(f"[JOB {self._tag}] {stage}: {message}", flush=True)
        self._emit("stage_started", stage=stage, stage_status=STAGE_RUNNING,
                   stage_progress=0.0, message=message)

    def progress(self, stage: str, fraction: float, message: Optional[str] = None,
                 counters: Optional[Dict[str, Any]] = None) -> None:
        self._emit("stage_progress", stage=stage, stage_progress=fraction,
                   message=message, counters=counters)

    def detail(self, stage: str, text: str, counters: Optional[Dict[str, Any]] = None) -> None:
        print(f"[JOB {self._tag}] {stage}: {text}", flush=True)
        self._emit("stage_detail", stage=stage, detail=text, message=text, counters=counters)

    def stage_completed(self, stage: str, message: str,
                        counters: Optional[Dict[str, Any]] = None) -> None:
        print(f"[JOB {self._tag}] {stage} done: {message}", flush=True)
        self._emit("stage_completed", stage=stage, stage_status=STAGE_DONE,
                   message=message, counters=counters)

    def stage_skipped(self, stage: str, message: str) -> None:
        self._emit("stage_skipped", stage=stage, stage_status=STAGE_SKIPPED, message=message)

    def completed(self, result: Dict[str, Any], message: str = "Processing complete") -> None:
        print(f"[JOB {self._tag}] completed", flush=True)
        self._emit("job_completed", stage="complete", stage_status=STAGE_DONE,
                   message=message, result=result)

    def failed(self, error: str) -> None:
        print(f"[JOB {self._tag}] FAILED: {error}", flush=True)
        self._emit("job_failed", error=error, message=error)


job_store: JobStore = InMemoryJobStore()

# Dedicated workers so long PDF jobs don't occupy the request threadpool.
_job_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="paimana-job")


def create_job(kind: str, stages, metadata: Optional[Dict[str, Any]] = None) -> str:
    return job_store.create(kind, stages, metadata)


def submit_job(job_id: str, target: Callable[..., None], *args, **kwargs) -> None:
    reporter = JobReporter(job_store, job_id)

    def runner():
        try:
            target(reporter, *args, **kwargs)
        except Exception as exc:  # last-resort guard; pipelines report their own errors
            reporter.failed(f"Unexpected error: {exc}")

    _job_executor.submit(runner)
