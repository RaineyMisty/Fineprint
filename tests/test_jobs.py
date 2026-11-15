"""Background work must survive alternating replicas and never block a poll."""
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
import io
import threading
import time
import unittest
from unittest.mock import patch

from fineprint.compiler import FallbackCompiler
from fineprint.jobs import CompilationCache, JobStore, RETRY_MESSAGE
from fineprint.providers import ProviderError
from fineprint.repository import sample_inputs
from fineprint.server import Handler, Server


class JobHttpTests(unittest.TestCase):
    def setUp(self):
        self.servers = []
        for _ in range(2):
            server = Server(("127.0.0.1", 0), Handler)
            server.job_store = JobStore()
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self.servers.append((server, thread))

    def tearDown(self):
        for server, thread in self.servers:
            server.shutdown()
            server.server_close()
            thread.join()
            server.job_store.executor.shutdown(wait=True)

    def post(self, replica, path, envelope, headers=None, *, raw=None, method="POST"):
        conn = HTTPConnection("127.0.0.1", self.servers[replica][0].server_port, timeout=3)
        started = time.monotonic()
        conn.request(method, path, raw if raw is not None else (None if method in ("GET", "HEAD") else json.dumps(envelope)), headers or {"Content-Type": "application/json"})
        response = conn.getresponse()
        data = response.read()
        result = json.loads(data) if data and response.getheader("Content-Type", "").startswith("application/json") else None
        status = response.status
        conn.close()
        self.assertLess(time.monotonic() - started, 1)
        return status, result

    def finish(self, replica, path, envelope):
        for _ in range(100):
            status, body = self.post(replica, path, envelope)
            if body["status"] != "running":
                return status, body
            time.sleep(.01)
        self.fail("Job did not finish")

    def test_poll_on_other_replica_resumes_once_and_returns_same_result(self):
        gate = threading.Event()
        calls = []
        envelope = {"operation": "/api/compile", "payload": {"document": "policy"}}
        def slow(*args, **kwargs):
            calls.append(args)
            gate.wait(3)
            return {"value": 38500}
        with patch("fineprint.server.execute", side_effect=slow):
            try:
                status, body = self.post(0, "/api/jobs", envelope)
                self.assertEqual(status, 202)
                path = "/api/jobs/" + body["job_id"]
                for replica in [1, 0, 1, 0]:
                    status, body = self.post(replica, path, envelope)
                    self.assertEqual((status, body["status"]), (202, "running"))
                gate.set()
                for replica in [0, 1]:
                    status, body = self.finish(replica, path, envelope)
                    self.assertEqual(status, 200)
                    self.assertEqual(body["result"], {"value": 38500})
                self.assertEqual(len(calls), 2)
                self.assertEqual(self.post(0, path, {**envelope, "payload": {}})[0], 400)
            finally:
                gate.set()

    def test_all_browser_operations_use_real_worker_pipeline(self):
        with patch.dict("os.environ", {"FINEPRINT_LLM_PROVIDER": "fallback"}):
            inputs = sample_inputs("aurora-imaging")["inputs"]
            compile_job = dict(operation="/api/compile", payload=dict(document=inputs["policy"], provider="fallback"))
            _, body = self.post(0, "/api/jobs", compile_job)
            _, body = self.finish(0, "/api/jobs/" + body["job_id"], compile_job)
            checked = dict(operation="/api/check", payload={**inputs, **body["result"]})
            _, body = self.post(1, "/api/jobs", checked)
            _, body = self.finish(1, "/api/jobs/" + body["job_id"], checked)
            self.assertEqual(body["status"], "done")
            self.assertEqual(body["result"]["report"]["summary"]["illustrated_max_patient_cents"], 38500)

    def test_legacy_slow_request_also_returns_a_resumable_job(self):
        gate = threading.Event()
        payload = {"document": "policy"}
        def slow(*args, **kwargs):
            gate.wait(3)
            return {"done": True}
        with patch("fineprint.server.execute", side_effect=slow), patch("fineprint.server.LEGACY_WAIT_SECONDS", .02):
            try:
                status, body = self.post(0, "/api/compile", payload)
                self.assertEqual((status, body["status"]), (202, "running"))
                gate.set()
                envelope = dict(operation="/api/compile", payload=payload)
                _, result = self.finish(1, "/api/jobs/" + body["job_id"], envelope)
                self.assertEqual(result["result"], {"done": True})
            finally:
                gate.set()

    def test_provider_and_unexpected_errors_are_friendly_and_retryable(self):
        envelope = dict(operation="/api/compile", payload={})
        for exc in (ProviderError("Provider HTTP 504"), RuntimeError("secret internals")):
            with patch("fineprint.server.execute", side_effect=exc):
                _, body = self.post(0, "/api/jobs", envelope)
                _, body = self.finish(0, "/api/jobs/" + body["job_id"], envelope)
                self.assertEqual((body["status"], body["kind"], body["error"]), ("failed", "retry", RETRY_MESSAGE))

    def test_guards_apply_to_job_start_and_poll(self):
        for path in ("/api/jobs", "/api/jobs/" + "a" * 32):
            self.assertEqual(self.post(0, path, {})[0], 400)
            self.assertEqual(self.post(0, path, {}, {"Content-Type": "text/plain"})[0], 400)
            self.assertEqual(self.post(0, path, {}, {"Content-Type": "application/json", "Sec-Fetch-Site": "cross-site"})[0], 403)
        self.assertEqual(self.post(0, "/api/jobs/invalid", dict(operation="/api/check", payload={}))[0], 400)

    def test_empty_malformed_and_wrong_task_get_have_no_server_errors(self):
        for replica in (0, 1):
            for path in ("/api/jobs", "/api/jobs/" + "a" * 32):
                for raw in (b"", b"{", b"null", b"[]", b"{}", b'\xff',
                            b'{"operation":[],"payload":{}}', b'{"operation":{},"payload":{}}',
                            b'{"operation":"/api/check","payload":[]}'):
                    self.assertEqual(self.post(replica, path, None, raw=raw)[0], 400)
            status, body = self.post(replica, "/api/jobs/" + "a" * 32, None, method="GET")
            self.assertEqual((status, body["status"]), (202, "resume_required"))

    def test_full_store_does_not_block_health_or_emit_5xx(self):
        gate = threading.Event()
        envelope = dict(operation="/api/compile", payload={})
        def slow(*args, **kwargs):
            gate.wait(3)
            return {}
        self.servers[0][0].job_store.limit = 1
        with patch("fineprint.server.execute", side_effect=slow):
            try:
                self.assertEqual(self.post(0, "/api/jobs", envelope)[0], 202)
                for _ in range(6):
                    status, body = self.post(0, "/api/jobs", envelope)
                    self.assertEqual((status, body["status"]), (202, "busy"))
                with ThreadPoolExecutor(max_workers=16) as pool:
                    requests = [(method, path) for method in ("GET", "HEAD")
                                for path in ("/", "/ping", "/health", "/healthz", "/ready", "/readyz", "/livez")]
                    statuses = list(pool.map(lambda item: self.post(0, item[1], None, method=item[0])[0], requests))
                self.assertEqual(statuses, [200] * len(requests))
                self.assertEqual(len(self.servers[0][0].job_store.jobs), 1)
                self.assertEqual(self.post(0, "/ping", None, method="OPTIONS")[0], 405)
            finally:
                gate.set()

    def test_access_logs_include_status_and_timing_without_query_or_body(self):
        output = io.StringIO()
        with patch("sys.stdout", output):
            self.assertEqual(self.post(0, "/ping?token=private-value", None, method="GET")[0], 200)
            time.sleep(.02)  # Handler logs once after the response is written.
        logs = [json.loads(line) for line in output.getvalue().splitlines() if line.startswith('{')]
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["method"], "GET")
        self.assertEqual(logs[0]["path"], "/ping")
        self.assertEqual(logs[0]["status"], 200)
        self.assertIn("ms", logs[0])
        self.assertNotIn("private-value", output.getvalue())


class JobStoreTests(unittest.TestCase):
    def test_capacity_and_expiry_are_bounded(self):
        store = JobStore(limit=1, ttl=.01)
        gate = threading.Event()
        envelope = dict(operation="/api/check", payload={})
        try:
            _, first = store.poll(envelope, lambda *_: gate.wait(2))
            status, body = store.poll(envelope, lambda *_: None)
            self.assertEqual((status, body["status"]), (202, "busy"))
            gate.set()
            store.executor.shutdown(wait=True)
            time.sleep(.02)
            # Pruning does not require a background timer or a growing history.
            store.executor = ThreadPoolExecutor(max_workers=1)
            _, second = store.poll(envelope, lambda *_: None)
            self.assertNotEqual(first["job_id"], second["job_id"])
            self.assertEqual(len(store.jobs), 1)
        finally:
            gate.set()
            store.executor.shutdown(wait=True)

    def test_completed_jobs_are_evicted_before_capacity_response(self):
        store = JobStore(limit=2)
        envelope = dict(operation="/api/check", payload={})
        try:
            for _ in range(40):
                status, body = store.poll(envelope, lambda *_: {"ok": True}, wait_seconds=.1)
                self.assertEqual((status, body["status"]), (200, "done"))
                self.assertLessEqual(len(store.jobs), 2)
        finally:
            store.executor.shutdown(wait=True)

    def test_compile_cache_singleflight_provenance_and_mutation_isolation(self):
        cache = CompilationCache()
        compiler = FallbackCompiler()
        text = sample_inputs("aurora-imaging")["inputs"]["policy"]
        with patch.object(compiler, "compile", wraps=compiler.compile) as compile_call:
            with ThreadPoolExecutor(max_workers=3) as pool:
                results = list(pool.map(lambda _: cache.compile(text, "one", compiler), range(3)))
            self.assertEqual(compile_call.call_count, 1)
            results[0].output.warnings.append("client mutation")
            self.assertNotIn("client mutation", cache.compile(text, "one", compiler).output.warnings)
            self.assertEqual(cache.compile(text, "two", compiler).source_document_id, "two")
            self.assertEqual(compile_call.call_count, 2)
        with patch.object(compiler, "compile", side_effect=ProviderError("retry")) as failing:
            for _ in range(2):
                with self.assertRaises(ProviderError):
                    cache.compile(text, "failure", compiler)
            self.assertEqual(failing.call_count, 2)
