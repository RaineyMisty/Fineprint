"""Exercise the PDF upload contract over HTTP, including its handoff to the pipeline."""

import base64
import importlib.util
import json
import unittest
from http.client import HTTPConnection

from fineprint.documents_pdf import NO_TEXT_ERROR, PDF_NOTICE, SCHEMA_ERROR, UNREADABLE_ERROR
from fineprint.server import MAX_BODY
from tests import test_server
from tests.pdf_helpers import pdf_bytes


class PdfEndpointValidationTests(unittest.TestCase):
    setUpClass = classmethod(test_server.ServerTests.setUpClass.__func__)
    tearDownClass = classmethod(test_server.ServerTests.tearDownClass.__func__)
    request = test_server.ServerTests.request

    def extract(self, data, kind="policy", filename="document.pdf"):
        return self.request("POST", "/api/extract", json.dumps({
            "kind": kind, "filename": filename, "content_base64": base64.b64encode(data).decode()
        }), {"Content-Type": "application/json"})

    def test_schema_base64_and_http_guards(self):
        for body, message in (({}, SCHEMA_ERROR),
                              ({"kind": "policy", "filename": "bad.pdf", "content_base64": "!?"}, UNREADABLE_ERROR)):
            status, _, error = self.request("POST", "/api/extract", json.dumps(body), {"Content-Type": "application/json"})
            self.assertEqual((status, error), (400, {"error": message, "kind": "input"}))
        self.assertEqual(self.extract(b"not a PDF")[2], {"error": UNREADABLE_ERROR, "kind": "input"})
        self.assertEqual(self.request("POST", "/api/extract", "{}", {"Content-Type": "text/plain"})[0], 415)
        self.assertEqual(self.request("POST", "/api/extract", "{}", {
            "Content-Type": "application/json", "Sec-Fetch-Site": "cross-site"})[0], 403)

    def test_oversized_body_rejected_before_read(self):
        self.assertEqual(MAX_BODY, 15 * 1024 * 1024)
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            connection.putrequest("POST", "/api/extract")
            connection.putheader("Content-Type", "application/json")
            connection.putheader("Content-Length", str(MAX_BODY + 1))
            connection.endheaders()
            response = connection.getresponse()
            self.assertEqual(response.status, 413)
            self.assertEqual(json.loads(response.read()), {"error": "Request body must be between 1 byte and 15 MiB"})
        finally:
            connection.close()

    @unittest.skipUnless(importlib.util.find_spec("pypdf"), "pypdf is not installed; use the project .venv")
    def test_pdf_upload_succeeds_and_no_text_is_an_input_error(self):
        for kind in ("policy", "eob", "bill"):
            with self.subTest(kind=kind):
                status, _, result = self.extract(pdf_bytes("Selectable policy or statement text."), kind)
                self.assertEqual(status, 200)
                self.assertEqual(result["kind"], kind)
                self.assertEqual((result["filename"], result["pages"], result["status"]), ("document.pdf", 1, "text"))
                self.assertEqual(result["chars"], len(result["text"]))
                self.assertEqual(result["notice"], PDF_NOTICE)
                self.assertEqual(result["extracted_fields"], ["text"])
        status, _, error = self.extract(pdf_bytes(None))
        self.assertEqual((status, error), (400, {"error": NO_TEXT_ERROR, "kind": "input"}))

    @unittest.skipUnless(importlib.util.find_spec("pypdf"), "pypdf is not installed; use the project .venv")
    def test_extracted_documents_flow_into_compile_and_check(self):
        inputs = self.request("GET", "/api/samples/aurora-imaging")[2]["inputs"]
        baseline = self.request("POST", "/api/check", json.dumps(inputs), {"Content-Type": "application/json"})[2]
        for kind in ("policy", "eob", "bill"):
            status, _, result = self.extract(pdf_bytes(inputs[kind]), kind)
            self.assertEqual(status, 200)
            self.assertEqual(result["status"], "text" if kind == "policy" else "structured")
            inputs[kind] = result["text"]
        status, _, compilation = self.request("POST", "/api/compile", json.dumps({"document": inputs["policy"]}),
                                               {"Content-Type": "application/json"})
        self.assertEqual(status, 200)
        self.assertEqual(compilation["compilation"]["backend"], "fallback")
        status, _, checked = self.request("POST", "/api/check", json.dumps(inputs), {"Content-Type": "application/json"})
        self.assertEqual(status, 200)
        self.assertEqual(checked["report"]["summary"], baseline["report"]["summary"])


if __name__ == "__main__":
    unittest.main()
