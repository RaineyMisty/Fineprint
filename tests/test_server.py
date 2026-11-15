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
        # The server may reject an oversized body before reading it; a reset/broken pipe is also a rejection.
        try:
            status = self.request("POST", "/api/analyze", "x" * (1024 * 1024 + 1), {"Content-Type": "application/json"})[0]
        except (BrokenPipeError, ConnectionResetError):
            return
        self.assertEqual(status, 413)

    def test_unknown_routes_and_traversal(self):
        for path in ("/api/cases/missing", "/api/cases/../policy.json", "/../pyproject.toml"):
            self.assertEqual(self.request("GET", path)[0], 404)
        self.assertEqual(self.request("POST", "/missing", "{}")[0], 404)

    def test_cross_site_browser_requests_rejected(self):
        self.assertEqual(self.request("POST", "/api/analyze", "{}", {"Content-Type": "application/json", "Sec-Fetch-Site": "cross-site"})[0], 403)


class CompilerServerTests(unittest.TestCase):
    setUpClass = classmethod(ServerTests.setUpClass.__func__)
    tearDownClass = classmethod(ServerTests.tearDownClass.__func__)
    request = ServerTests.request
    def test_compile_text_standalone_and_into_case(self):
        data=self.request("GET","/api/cases/aurora-imaging")[2]
        self.assertEqual(data["compilation"]["backend"],"fallback")
        document=data["documents"]["policy"].replace("$25 copay","$30 copay")
        status,_,standalone=self.request("POST","/api/compile",json.dumps({"document":document}),{"Content-Type":"application/json"})
        self.assertEqual(status,200)
        self.assertEqual(standalone["compilation"]["output"]["policy"]["benefits"][0]["copay_cents"],3000)
        status,_,result=self.request("POST","/api/compile",json.dumps({"document":document,"case":data["case"]}),{"Content-Type":"application/json"})
        self.assertEqual(status,200)
        self.assertEqual(result["report"]["summary"]["illustrated_min_patient_cents"],39000)

    def test_unsupported_clause_and_mismatched_policy_block_calculation(self):
        data=self.request("GET","/api/cases/aurora-imaging")[2]
        for old,new in [("deductible then 20% member coinsurance","subject to administrator discretion"),
                        ("POL-SYN-A01","OTHER-POLICY")]:
            document=data["documents"]["policy"].replace(old,new)
            status,_,result=self.request("POST","/api/compile",json.dumps({"document":document,"case":data["case"]}),{"Content-Type":"application/json"})
            self.assertEqual(status,200)
            self.assertEqual(result["report"]["status"],"blocked")
            self.assertFalse(result["report"]["scenarios"])

    def test_compile_request_schema_and_offline_metrics(self):
        for payload in ({"document":True},{"document":""},{"document":"text","unknown":1}):
            self.assertEqual(self.request("POST","/api/compile",json.dumps(payload),{"Content-Type":"application/json"})[0],400)
        status,_,report=self.request("GET","/api/evaluation")
        self.assertEqual(status,200)
        self.assertEqual(report["backend"],"fallback")
        self.assertEqual(report["groups"]["all"]["calculation"]["exact"],8)


class CheckEndpointTests(unittest.TestCase):
    setUpClass = classmethod(ServerTests.setUpClass.__func__)
    tearDownClass = classmethod(ServerTests.tearDownClass.__func__)
    request = ServerTests.request

    def check(self, inputs):
        return self.request("POST", "/api/check", json.dumps(inputs), {"Content-Type": "application/json"})

    def test_status_and_samples(self):
        self.assertIn("provider", self.request("GET", "/api/status")[2])
        self.assertEqual(len(self.request("GET", "/api/samples")[2]), 3)
        sample = self.request("GET", "/api/samples/aurora-imaging")[2]
        self.assertEqual(set(sample["inputs"]) >= {"policy", "eob", "bill", "claim_format"}, True)
        self.assertEqual(self.request("GET", "/api/samples/missing")[0], 404)

    def test_check_pasted_documents_matches_case_endpoint(self):
        for case_id in ("aurora-imaging", "mosaic-oop", "mosaic-therapy"):
            inputs = self.request("GET", "/api/samples/" + case_id)[2]["inputs"]
            status, _, data = self.check(inputs)
            self.assertEqual(status, 200)
            expected = self.request("GET", "/api/cases/" + case_id)[2]["report"]["summary"]
            self.assertEqual(data["report"]["summary"], expected)
            self.assertEqual(data["compilation"]["backend"], "fallback")

    def test_check_unresolved_clause_blocks_and_bad_input_is_400(self):
        inputs = self.request("GET", "/api/samples/aurora-imaging")[2]["inputs"]
        bad = dict(inputs, policy=inputs["policy"].replace("deductible then 20% member coinsurance", "subject to administrator discretion"))
        data = self.check(bad)[2]
        self.assertEqual(data["report"]["status"], "blocked")
        self.assertTrue(data["compilation"]["output"]["unresolved"])
        status, _, err = self.check(dict(inputs, eob="not,a,claim"))
        self.assertEqual((status, err["kind"]), (400, "input"))
        self.assertEqual(self.check(dict(inputs, claim_format="nope"))[0], 400)
        self.assertEqual(self.check({"policy": "x"})[0], 400)
