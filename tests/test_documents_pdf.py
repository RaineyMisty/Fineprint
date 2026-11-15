import base64
import importlib.util
import unittest
from unittest.mock import patch

from fineprint import documents_pdf as pdf
from fineprint.repository import sample_inputs
from tests.pdf_helpers import pdf_bytes

HAS_PYPDF = importlib.util.find_spec("pypdf") is not None


class PdfTableTests(unittest.TestCase):
    def setUp(self):
        self.inputs = sample_inputs("aurora-imaging")["inputs"]

    def test_supported_tables_preserve_values(self):
        for kind, fmt in (("eob", "aurora-csv-v1"), ("bill", "bill-csv")):
            with self.subTest(kind=kind):
                text = self.inputs[kind]
                parsed = pdf.find_table(text, kind)
                self.assertEqual(parsed[0], fmt)
                self.assertEqual(parsed[1].strip(), text.strip())
                self.assertGreater(parsed[2], 0)

    def test_never_accepts_a_partial_or_malformed_table(self):
        for kind in ("eob", "bill"):
            text = self.inputs[kind].strip()
            header, row, *_ = text.splitlines()
            for broken in (text + "\ntruncated,row", text + '\n"unterminated',
                           header + "\n" + row.rsplit(",", 1)[0] + ",NaN",
                           header + "\n" + row.rsplit(",", 1)[0] + ",-1",
                           header + "\n" + row.rsplit(",", 1)[0] + ",1.001",
                           header + "\n" + row.replace(row.split(",")[0], "", 1),
                           header):
                with self.subTest(kind=kind, broken=broken[-40:]):
                    self.assertIsNone(pdf.find_table(broken, kind))

    def test_header_case_is_normalized_for_existing_adapters(self):
        text = self.inputs["bill"]
        header, rest = text.split("\n", 1)
        parsed = pdf.find_table(header.upper() + "\n" + rest, "bill")
        self.assertEqual(parsed[1].splitlines()[0], header)
        self.assertEqual(parsed[3], header.split(","))


@unittest.skipUnless(HAS_PYPDF, "pypdf is not installed; use the project .venv")
class PdfExtractionTests(unittest.TestCase):
    def test_selectable_text_and_short_text_are_preserved(self):
        for text in ("Hello policy benefits and deductible.", "Hi"):
            with self.subTest(text=text):
                result = pdf.extract_pdf_text(pdf_bytes(text))
                self.assertEqual(result["pages"], 1)
                self.assertEqual(result["text"], text)
                self.assertEqual(result["chars"], len(text))

    def test_no_text_fails_with_contract_message(self):
        for pages in ((None,), (None, None), ("   ",)):
            with self.subTest(pages=pages), self.assertRaises(pdf.PdfError) as error:
                pdf.extract_pdf_text(pdf_bytes(*pages))
            self.assertEqual(str(error.exception), pdf.NO_TEXT_ERROR)

    def test_invalid_and_encrypted_documents(self):
        for data in (b"not a PDF", b"%PDF-1.7\ncorrupt"):
            with self.subTest(data=data), self.assertRaises(pdf.PdfError) as error:
                pdf.extract_pdf_text(data)
            self.assertEqual(str(error.exception), pdf.UNREADABLE_ERROR)
        with self.assertRaises(pdf.PdfError) as error:
            pdf.extract_pdf_text(pdf_bytes("Password protected policy", password="secret"))
        self.assertEqual(str(error.exception), pdf.PASSWORD_ERROR)
        self.assertIn("Policy", pdf.extract_pdf_text(pdf_bytes("Policy", password=""))["text"])

    def test_page_breaks_and_unreadable_page_warning(self):
        result = pdf.extract_upload("policy", "policy.pdf", pdf_bytes("Page one", None, "Page three"))
        self.assertEqual(result["pages"], 3)
        self.assertEqual(result["text"], "Page one\n\f\nPage three")
        self.assertIn("1 of 3 pages", result["warnings"][0])

    def test_supported_tables_and_unstructured_review_fallback(self):
        inputs = sample_inputs("aurora-imaging")["inputs"]
        for kind in ("eob", "bill"):
            with self.subTest(kind=kind):
                result = pdf.extract_upload(kind, kind + ".pdf", pdf_bytes(inputs[kind]))
                self.assertEqual(result["status"], "structured")
                self.assertEqual(result["text"].strip(), inputs[kind].strip())
                self.assertGreater(result["rows"], 0)
                self.assertEqual(result["notice"], pdf.PDF_NOTICE)
                self.assertEqual(result["extracted_fields"], inputs[kind].splitlines()[0].split(","))
                raw = "Insurer statement: amount owed $25.00. Please review."
                fallback = pdf.extract_upload(kind, kind + ".pdf", pdf_bytes(raw))
                self.assertEqual(fallback["text"], raw)
                self.assertEqual((fallback["status"], fallback["rows"], fallback["format"]), ("text", 0, None))
                self.assertEqual(fallback["extracted_fields"], ["text"])
                self.assertTrue(fallback["warnings"])
        policy = pdf.extract_upload("policy", "policy.pdf", pdf_bytes(inputs["bill"]))
        self.assertEqual(policy["status"], "text")

    def test_request_validation_and_raw_size_limit(self):
        payload = {"kind": "policy", "filename": "policy.pdf",
                   "content_base64": base64.b64encode(pdf_bytes("Policy text")).decode()}
        self.assertEqual(pdf.extract_request(payload)["text"], "Policy text")
        for invalid in ({}, [], dict(payload, kind="other"), dict(payload, filename=" "),
                        dict(payload, filename=123), dict(payload, content_base64=None),
                        dict(payload, extra=True)):
            with self.subTest(invalid=invalid), self.assertRaises(pdf.PdfError) as error:
                pdf.extract_request(invalid)
            self.assertEqual(str(error.exception), pdf.SCHEMA_ERROR)
        with self.assertRaises(pdf.PdfError) as error:
            pdf.extract_request(dict(payload, content_base64="!!not base64!!"))
        self.assertEqual(str(error.exception), pdf.UNREADABLE_ERROR)
        with patch.object(pdf, "MAX_PDF_BYTES", 8), self.assertRaises(pdf.PdfError) as error:
            pdf.extract_request(payload)
        self.assertEqual(str(error.exception), "PDF is larger than 11 MB")


if __name__ == "__main__":
    unittest.main()
