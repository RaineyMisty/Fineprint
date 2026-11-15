"""Verify the browser's resumable HTTP contract against one or more real servers.

Alternating independent servers simulates an ECS load balancer without affinity.
Reports contain timings and hashes, never uploaded PDFs, text, or credentials.
"""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import secrets
import threading
import time
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", action="append", required=True)
    parser.add_argument("--policy-pdf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    requests, stages, runs = [], [], []
    lock = threading.Lock()

    def call(base, path, body=None):
        started = time.monotonic()
        req = Request(base + path, data=None if body is None else json.dumps(body).encode(),
                      headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=18) as response:
            result = json.load(response)
            status = response.status
        elapsed = time.monotonic() - started
        with lock:
            requests.append(dict(server=base, path=path, status=status, seconds=round(elapsed, 4)))
        assert elapsed < 20, (path, elapsed)
        return result

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
    report = dict(passed=True, provider="deepseek", pdf_sha256=hashlib.sha256(pdf).hexdigest(),
                  replicas=len(args.base_url), runs=runs, stages=stages, requests=requests,
                  max_request_seconds=max(r["seconds"] for r in requests))
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(dict(passed=True, requests=len(requests), max_request_seconds=report["max_request_seconds"])), flush=True)


if __name__ == "__main__":
    main()
