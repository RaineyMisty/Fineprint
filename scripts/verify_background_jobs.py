"""Verify the browser's resumable HTTP contract against one or more real servers.

Alternating independent servers simulates an ECS load balancer without affinity.
Reports contain timings and hashes, never uploaded PDFs, text, or credentials.
"""
import argparse
import base64
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import secrets
import threading
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", action="append", required=True)
    parser.add_argument("--policy-pdf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    requests, stages, runs = [], [], []
    lock = threading.Lock()

    def call(base, path, body=None, *, raw=None, expected=None, method=None):
        started = time.monotonic()
        req = Request(base + path, data=raw if raw is not None else (None if body is None else json.dumps(body).encode()),
                      headers={"Content-Type": "application/json"}, method=method)
        try:
            response = urlopen(req, timeout=5)
        except HTTPError as exc:
            response = exc
        with response:
            data = response.read()
            status = response.status
            result = json.loads(data) if data and response.headers.get_content_type() == "application/json" else None
        elapsed = time.monotonic() - started
        with lock:
            requests.append(dict(server=base, path=path, method=req.get_method(), status=status, seconds=round(elapsed, 4),
                                 intentional_invalid=expected == 400))
        assert elapsed < 3, (path, elapsed)
        assert status < 500, (path, status)
        assert status == expected if expected is not None else status in (200, 202, 204), (path, status)
        return result

    # Invalid probes must be predictable 400s, never unhandled exceptions/5xx.
    for base in args.base_url:
        for path in ("/api/jobs", "/api/jobs/" + "a" * 32):
            for raw in (b"", b"{", b"null", b"[]", b"{}", b'{"operation":[],"payload":{}}',
                        b'{"operation":"/api/check","payload":[]}', b'\xff'):
                call(base, path, raw=raw, expected=400, method="POST")
        call(base, "/api/jobs/" + "b" * 32)  # Unknown-task GET is 202, never 404.

    stop_health, health_errors = threading.Event(), []
    def health_checks():
        while not stop_health.is_set():
            try:
                for base in args.base_url:
                    for path in ("/", "/ping", "/healthz"):
                        call(base, path, expected=200)
                    call(base, "/ping", expected=200, method="HEAD")
            except Exception as exc:
                health_errors.append(type(exc).__name__)
                return
            stop_health.wait(2)
    health_thread = threading.Thread(target=health_checks, daemon=True)
    health_thread.start()

    def job(operation, payload):
        started = time.monotonic()
        envelope = dict(operation=operation, payload=payload)
        job_id = secrets.token_urlsafe(24)
        # Require completion on BOTH tasks to prove a wrong-task poll resumes
        # work and neither task repeatedly starts its copy on every poll.
        completed = {}
        for poll in range(600):
            base = args.base_url[poll % len(args.base_url)]
            result = call(base, "/api/jobs/" + job_id, envelope)
            if result["status"] == "failed":
                raise AssertionError(result.get("error"))
            if result["status"] == "done":
                completed[base] = result["result"]
                if len(completed) == len(args.base_url):
                    elapsed = round(time.monotonic() - started, 3)
                    with lock:
                        stages.append(dict(operation=operation, seconds=elapsed, polls=poll + 1))
                    print(json.dumps(dict(operation=operation, seconds=elapsed, polls=poll + 1)), flush=True)
                    return result["result"]
            time.sleep(1.5)
        raise AssertionError("Job did not finish")

    pdf = args.policy_pdf.read_bytes()
    for number in (1, 2):
        started = time.monotonic()
        demo = call(args.base_url[0], "/api/demos/kaiser-real-sbc")
        extracted = job("/api/extract", dict(kind="policy", filename=args.policy_pdf.name,
                                            content_base64=base64.b64encode(pdf).decode()))
        inputs = {**demo["inputs"], "policy": extracted["text"], "sample_id": demo["id"]}
        compiled = job("/api/compile", dict(document=inputs["policy"], document_id=demo["id"] + "/policy.md", provider="deepseek"))
        assert compiled["compilation"]["backend"] == "deepseek"
        inputs["claim_context"]["policy_id"] = compiled["compilation"]["output"]["policy"]["id"]
        checked = job("/api/check", {**inputs, **compiled})
        summary = checked["report"]["summary"]
        assert checked["report"]["status"] == "ready"
        assert summary["illustrated_max_patient_cents"] <= summary["bill_patient_cents"]
        assert summary["illustrated_min_patient_cents"] == summary["illustrated_max_patient_cents"] == 5000
        run = dict(sample=demo["id"], run=number, seconds=round(time.monotonic() - started, 3),
                   patient_cents=summary["illustrated_max_patient_cents"], bill_cents=summary["bill_patient_cents"])
        runs.append(run)
        print(json.dumps(run), flush=True)

    def sample(case_id, expected):
        started = time.monotonic()
        data = call(args.base_url[0], "/api/samples/" + case_id)
        inputs = {**data["inputs"], "sample_id": case_id}
        compiled = job("/api/compile", dict(document=inputs["policy"], document_id=case_id + "/policy.md", provider="deepseek"))
        checked = job("/api/check", {**inputs, **compiled})
        summary = checked["report"]["summary"]
        assert checked["report"]["status"] == "ready"
        assert summary["illustrated_min_patient_cents"] == summary["illustrated_max_patient_cents"] == expected
        assert expected <= summary["bill_patient_cents"]
        run = dict(sample=case_id, seconds=round(time.monotonic() - started, 3), patient_cents=expected)
        with lock:
            runs.append(run)
        print(json.dumps(run), flush=True)

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(sample, name, expected) for name, expected in
                   (("aurora-imaging", 38500), ("mosaic-oop", 100000), ("mosaic-therapy", 4000))]
        for future in futures:
            future.result()
    stop_health.set()
    health_thread.join()
    assert not health_errors, health_errors
    tally = dict(Counter(str(r["status"]) for r in requests))
    report = dict(passed=True, provider="deepseek", pdf_sha256=hashlib.sha256(pdf).hexdigest(),
                  replicas=len(args.base_url), runs=runs, stages=stages, requests=requests,
                  status_codes=tally, health_errors=health_errors, zero_5xx=True,
                  max_request_seconds=max(r["seconds"] for r in requests))
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(dict(passed=True, requests=len(requests), max_request_seconds=report["max_request_seconds"], status_codes=tally)), flush=True)


if __name__ == "__main__":
    main()
