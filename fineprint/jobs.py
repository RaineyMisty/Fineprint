"""Bounded, ephemeral background jobs with client-carried replica resumption.

POST /jobs starts work; POST /jobs/<id> polls with the SAME operation/payload.
On another replica that poll starts its local copy exactly once. No task-to-task
network access, sticky sessions, shared filesystem, or AWS permissions are needed.
With two replicas there can be two provider calls; the browser takes the first
completed result. Restarted tasks can resume too. IDs are unguessable capabilities.
Inputs/results are kept only in memory, expire after 30 minutes, and are bounded.
"""

import hashlib
import json
import re
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass, field

from .models import ModelError

RETRY_MESSAGE = "This check didn’t finish. Please try again in a moment."
OPERATIONS = {"/api/extract", "/api/compile", "/api/check", "/api/analyze", "/api/case"}


@dataclass
class Job:
    fingerprint: str
    created: float = field(default_factory=time.monotonic)
    status: str = "running"
    result: object = None
    error: str = ""
    kind: str = "input"
    finished: threading.Event = field(default_factory=threading.Event)


class JobStore:
    def __init__(self, *, workers=4, limit=32, ttl=1800):
        self.executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="analysis")
        self.lock = threading.Lock()
        self.jobs = {}
        self.limit, self.ttl = limit, ttl

    def poll(self, envelope, execute, job_id=None, *, wait_seconds=0):
        if (not isinstance(envelope, dict) or set(envelope) != {"operation", "payload"}
                or not isinstance(envelope.get("operation"), str)
                or envelope["operation"] not in OPERATIONS
                or not isinstance(envelope.get("payload"), dict)):
            raise ModelError("Choose a supported document check")
        if job_id is not None and (not isinstance(job_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{32}", job_id)):
            raise ModelError("Please start this check again")
        fingerprint = hashlib.sha256(json.dumps(envelope, sort_keys=True, separators=(",", ":"),
                                               ensure_ascii=False).encode()).hexdigest()
        with self.lock:
            now = time.monotonic()
            for key, job in list(self.jobs.items()):
                if job.status != "running" and now - job.created > self.ttl:
                    del self.jobs[key]
            job_id = job_id or secrets.token_urlsafe(24)
            job = self.jobs.get(job_id)
            if job is None:
                # Finished work must not fill the store for the entire TTL.
                # An evicted job can be resumed from its client-carried envelope.
                if len(self.jobs) >= self.limit:
                    completed = next((key for key, value in self.jobs.items() if value.status != "running"), None)
                    if completed is not None:
                        del self.jobs[completed]
                if len(self.jobs) >= self.limit:
                    # This is admission backpressure, not a target failure. Do
                    # not queue work or create a retained job until space opens.
                    return 202, {"job_id": job_id, "status": "busy", "retry_after_seconds": 5}
                job = self.jobs[job_id] = Job(fingerprint)
                try:
                    self.executor.submit(self._run, job, envelope, execute)
                except RuntimeError:
                    job.status, job.error, job.kind = "failed", RETRY_MESSAGE, "retry"
                    job.finished.set()
            elif job.fingerprint != fingerprint:
                raise ModelError("The documents changed. Please start this check again")
        # Only the legacy API waits briefly for fast results. The browser's start
        # and polling calls always use wait_seconds=0.
        if wait_seconds:
            job.finished.wait(wait_seconds)
        with self.lock:
            body = {"job_id": job_id, "status": job.status}
            if job.status == "done":
                body["result"] = job.result
            elif job.status == "failed":
                body.update(error=job.error, kind=job.kind)
            return (202 if job.status == "running" else 200), body

    def status(self, job_id):
        """A GET on the other task asks for resumption, never a missing-job 404."""
        if not re.fullmatch(r"[A-Za-z0-9_-]{32}", job_id):
            raise ModelError("Please start this check again")
        with self.lock:
            job = self.jobs.get(job_id)
            if job is None:
                return 202, {"job_id": job_id, "status": "resume_required", "retry_after_seconds": 2,
                             "message": "Continue by posting the original operation and payload to this URL."}
            body = {"job_id": job_id, "status": job.status}
            if job.status == "done":
                body["result"] = job.result
            elif job.status == "failed":
                body.update(error=job.error, kind=job.kind)
            return (202 if job.status == "running" else 200), body

    def _run(self, job, envelope, execute):
        started = time.monotonic()
        try:
            result = execute(envelope["operation"], envelope["payload"])
            with self.lock:
                job.result, job.status = result, "done"
        except Exception as exc:
            from .providers import ProviderError
            # Provider/internal exceptions may contain codes or sensitive input.
            safe_input = isinstance(exc, ModelError) and not isinstance(exc, ProviderError)
            with self.lock:
                job.error = str(exc) if safe_input else RETRY_MESSAGE
                job.kind = "input" if safe_input else "retry"
                job.status = "failed"
        finally:
            job.finished.set()
            print(f"analysis_stage operation={envelope['operation']} status={job.status} seconds={time.monotonic() - started:.3f}", flush=True)


class CompilationCache:
    """Small process-local content cache; concurrent identical compiles share work.

    Only validated successful outputs are cached. Document ID, provider, and
    model/config are part of the key so source evidence and settings stay exact.
    No uploaded PDF, policy text, or compilation is ever written to disk.
    """
    def __init__(self, limit=16, ttl=1800):
        self.lock = threading.Lock()
        self.entries = {}
        self.limit, self.ttl = limit, ttl

    def compile(self, document, document_id, compiler):
        from concurrent.futures import Future
        key = (hashlib.sha256(document.encode()).hexdigest(), document_id, compiler.name,
               getattr(compiler, "model", None), repr(getattr(compiler, "request_config", None)))
        with self.lock:
            now = time.monotonic()
            for old, (created, future) in list(self.entries.items()):
                if future.done() and now - created > self.ttl:
                    del self.entries[old]
            cached = self.entries.get(key)
            owner = cached is None
            if owner:
                if len(self.entries) >= self.limit:
                    completed = next((k for k, (_, f) in self.entries.items() if f.done()), None)
                    if completed is not None:
                        del self.entries[completed]
                future = Future()
                if len(self.entries) < self.limit:
                    self.entries[key] = (now, future)
            else:
                _, future = cached
        if owner:
            try:
                future.set_result(compiler.compile(document, document_id))
            except Exception as exc:
                future.set_exception(exc)
                with self.lock:
                    self.entries.pop(key, None)
                raise
        return deepcopy(future.result())


JOBS = JobStore()
COMPILED = CompilationCache()
