import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from fineprint.server import Handler
from tests.helpers import payload


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self, method, path, body=None, headers=None):
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        status, content_type, raw = response.status, response.getheader("Content-Type"), response.read()
        connection.close()
        return status, content_type, json.loads(raw) if content_type.startswith("application/json") else raw

    def post(self, data):
        return self.request("POST", "/api/analyze", json.dumps(data), {"Content-Type": "application/json"})

    def test_static_assets(self):
        for path, content_type in (("/", "text/html"), ("/app.js", "text/javascript"), ("/styles.css", "text/css")):
            status, actual, body = self.request("GET", path)
            self.assertEqual(status, 200)
            self.assertTrue(actual.startswith(content_type))
            self.assertTrue(body)

    def test_case_catalog_and_analysis(self):
        self.assertEqual(len(self.request("GET", "/api/cases")[2]), 3)
        status, _, data = self.request("GET", "/api/cases/aurora-imaging")
        self.assertEqual(status, 200)
        self.assertEqual(data["report"]["summary"]["potential_overpayment_min_cents"], 12000)

    def test_stateless_import_and_recalculation(self):
        self.assertEqual(self.post(payload())[2]["report"]["status"], "ready")
        p = payload()
        p["policy"]["benefits"][0]["deductible_applies"] = False
        self.assertEqual(self.post(p)[2]["report"]["summary"]["illustrated_min_patient_cents"], 4000)
        self.assertEqual(self.post(payload())[2]["report"]["summary"]["illustrated_min_patient_cents"], 12000)

    def test_semantic_errors_reported_without_results(self):
        p = payload()
        p["bill"]["member_id"] = "wrong"
        status, _, result = self.post(p)
        self.assertEqual(status, 200)
        self.assertEqual(result["report"]["status"], "blocked")
        self.assertEqual(result["report"]["comparisons"], [])

    def test_invalid_json_and_schema(self):
        self.assertEqual(self.post({})[0], 400)
        self.assertEqual(self.request("POST", "/api/analyze", "{", {"Content-Type": "application/json"})[0], 400)
        self.assertEqual(self.request("POST", "/api/analyze", "{}", {"Content-Type": "text/plain"})[0], 415)

    def test_size_limit(self):
        self.assertEqual(self.request("POST", "/api/analyze", "x" * (1024 * 1024 + 1), {"Content-Type": "application/json"})[0], 413)

    def test_unknown_routes_and_traversal(self):
        for path in ("/api/cases/missing", "/api/cases/../policy.json", "/../pyproject.toml"):
            self.assertEqual(self.request("GET", path)[0], 404)
        self.assertEqual(self.request("POST", "/missing", "{}")[0], 404)

    def test_cross_site_browser_requests_rejected(self):
        self.assertEqual(self.request("POST", "/api/analyze", "{}", {"Content-Type": "application/json", "Sec-Fetch-Site": "cross-site"})[0], 403)
