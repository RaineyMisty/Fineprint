"""In-memory PDF text extraction for uploaded policies, EOBs and bills.

Uploads are decoded and parsed entirely in memory (nothing is written to disk). Text comes from the
PDF's own text layer via pypdf; scanned/image-only PDFs fail closed with NO_TEXT_ERROR instead of
being guessed at. EOB/bill PDFs are turned into the pipeline's CSV only when the PDF literally
contains a table with the expected header and every row validates; otherwise the raw text is
returned for the user to review. Everything returned is marked PDF_NOTICE, never as verified.
"""

import base64
import binascii
import csv
import io
import logging
import re

from .adapters import dollars
from .models import ModelError

NO_TEXT_ERROR = "This PDF has no selectable text; image/scan reading isn't supported yet"
PDF_NOTICE = "extracted from PDF — please check"
UNREADABLE_ERROR = "This file isn't a readable PDF"
PASSWORD_ERROR = "This PDF is password-protected; remove the password and upload it again"
SCHEMA_ERROR = "Expected kind (policy, eob or bill), filename and content_base64"
MAX_PDF_BYTES = 11 * 1024 * 1024
MAX_PAGES = 1500
KINDS = ("policy", "eob", "bill")
PAGE_BREAK = "\n\f\n"  # policy_sections splits long documents into pages on form feeds
MIN_PAGE_CHARS = 1     # only whitespace-only pages have no selectable text
MIN_DOCUMENT_CHARS = 1

# Column sets the existing adapters read (fineprint/adapters.py); extra columns are allowed.
TABLES = {
    "eob": ("aurora-csv-v1",
            ("line_ref", "provider", "service_day", "cpt_hcpcs", "description", "network", "charge", "allowed",
             "deductible", "copay", "coinsurance", "noncovered", "balance", "plan_paid", "adjustment"),
            ("charge", "allowed", "deductible", "copay", "coinsurance", "noncovered", "balance", "plan_paid", "adjustment"),
            ("line_ref", "provider", "service_day", "cpt_hcpcs", "network")),
    "bill": ("bill-csv",
             ("id", "claim_line_id", "provider_id", "service_date", "code", "charged", "insurance_paid",
              "adjustment", "patient_paid", "balance_due"),
             ("charged", "insurance_paid", "adjustment", "patient_paid", "balance_due"),
             ("id", "claim_line_id", "provider_id", "service_date", "code")),
}


class PdfError(ModelError):
    """A user-facing problem with an uploaded PDF (HTTP 400, kind "input")."""


def _pypdf():
    try:
        import pypdf
    except ImportError:  # pragma: no cover - depends on the environment
        raise PdfError("PDF reading is not available on this server (pypdf is not installed)") from None
    # Font/encoding warnings would otherwise go to stderr and could leak document details into logs.
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    return pypdf


def _clean(text):
    lines = [line.rstrip() for line in (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    text = "\n".join(lines).strip("\n")
    return re.sub(r"\n{4,}", "\n\n\n", text)


def _page_text(page):
    """Layout-preserving text (keeps table rows on one line); plain extraction as a fallback."""
    layout = plain = ""
    try:
        layout = _clean(page.extract_text(extraction_mode="layout"))
    except Exception:  # pypdf's layout mode is stricter about odd fonts; fall back below
        layout = ""
    if len(re.sub(r"\s", "", layout)) >= MIN_PAGE_CHARS:
        return layout
    try:
        plain = _clean(page.extract_text())
    except Exception:
        plain = ""
    return plain if len(re.sub(r"\s", "", plain)) > len(re.sub(r"\s", "", layout)) else layout


def _open(data):
    if not isinstance(data, (bytes, bytearray)) or b"%PDF-" not in bytes(data[:1024]):
        raise PdfError(UNREADABLE_ERROR)
    pypdf = _pypdf()
    try:
        reader = pypdf.PdfReader(io.BytesIO(bytes(data)))
        if reader.is_encrypted:
            # Many insurer PDFs are encrypted with an empty user password (permissions only).
            try:
                opened = reader.decrypt("")
            except pypdf.errors.DependencyError:
                raise PdfError("This PDF uses encryption this server can't open") from None
            if not opened:
                raise PdfError(PASSWORD_ERROR)
        pages = list(reader.pages)
    except PdfError:
        raise
    except pypdf.errors.DependencyError:
        raise PdfError("This PDF uses encryption this server can't open") from None
    except Exception:
        raise PdfError(UNREADABLE_ERROR) from None
    if not pages:
        raise PdfError(UNREADABLE_ERROR)
    if len(pages) > MAX_PAGES:
        raise PdfError(f"This PDF has more than {MAX_PAGES} pages; upload the relevant part only")
    return pages


def _extract(data, plain=False):
    pages = _open(data)
    texts, failed = [], 0
    for page in pages:
        try:
            texts.append(_clean(page.extract_text()) if plain else _page_text(page))
        except Exception:
            texts.append("")
            failed += 1
    if failed == len(pages):
        raise PdfError(UNREADABLE_ERROR)
    if sum(len(re.sub(r"\s", "", t)) for t in texts) < MIN_DOCUMENT_CHARS:
        raise PdfError(NO_TEXT_ERROR)
    return texts


def extract_pdf_text(data):
    """PDF bytes -> {"pages", "chars", "text"}; raises PdfError (NO_TEXT_ERROR for scans/blank pages)."""
    texts = _extract(data)
    text = PAGE_BREAK.join(t for t in texts if len(re.sub(r"\s", "", t)) >= MIN_PAGE_CHARS)
    empty = sum(1 for t in texts if len(re.sub(r"\s", "", t)) < MIN_PAGE_CHARS)
    return {"pages": len(texts), "chars": len(text), "text": text, "empty_pages": empty}


def _row(line):
    try:
        return [cell.strip() for cell in next(csv.reader([line.strip()], strict=True))]
    except (csv.Error, StopIteration):
        return []


def find_table(text, kind):
    """Return (format, csv_text, rows, header) when `text` contains a confidently parseable table, else None.

    Confident means: a line whose CSV cells include every column the adapter needs, followed by rows that
    each have exactly as many cells, nonempty identifiers and exact dollar amounts the adapter accepts.
    Any malformed row after the header rejects the whole table (no partial or guessed lines)."""
    fmt, columns, money, required = TABLES[kind]
    lines = text.replace("\f", "\n").split("\n")
    for start, line in enumerate(lines):
        header = _row(line) if "," in line else []
        lowered = [cell.lower() for cell in header]
        if not header or len(set(lowered)) != len(lowered) or not set(columns) <= set(lowered):
            continue
        index = {name: lowered.index(name) for name in columns}
        rows = []
        for candidate in lines[start + 1:]:
            if not candidate.strip():
                continue
            cells = _row(candidate)
            if [cell.lower() for cell in cells] == lowered:
                continue  # header repeated on a following page
            if len(cells) != len(header):
                return None
            try:
                for name in money:
                    dollars(cells[index[name]])
            except ModelError:
                return None
            if not all(cells[index[name]] for name in required):
                return None
            rows.append(cells)
        if not rows:
            return None
        out = io.StringIO()
        writer = csv.writer(out, lineterminator="\n")
        writer.writerow(lowered)
        writer.writerows(rows)
        return fmt, out.getvalue(), len(rows), lowered
    return None


def extract_upload(kind, filename, data):
    """Uploaded PDF bytes -> the /api/extract response body (see module docstring)."""
    if kind not in KINDS:
        raise PdfError(SCHEMA_ERROR)
    if len(data) > MAX_PDF_BYTES:
        raise PdfError("PDF is larger than 11 MB")
    texts = _extract(data)
    kept = [t for t in texts if len(re.sub(r"\s", "", t)) >= MIN_PAGE_CHARS]
    text = PAGE_BREAK.join(kept)
    warnings = []
    empty = len(texts) - len(kept)
    if empty:
        warnings.append(f"{empty} of {len(texts)} pages had no selectable text (scanned images?) and were skipped"
                        + ("; most of this document could not be read" if empty * 2 >= len(texts) else ""))
    result = {"kind": kind, "filename": filename, "pages": len(texts), "chars": len(text), "status": "text",
              "text": text, "format": None, "rows": 0, "extracted_fields": ["text"], "notice": PDF_NOTICE,
              "warnings": warnings}
    if kind in TABLES:
        table = find_table(text, kind)
        if table is None:
            # Layout spacing can split cells; the plain text layer keeps CSV lines intact.
            table = find_table(PAGE_BREAK.join(_extract(data, plain=True)), kind)
        if table:
            fmt, csv_text, rows, header = table
            result.update(status="structured", text=csv_text, format=fmt, rows=rows, extracted_fields=header)
        else:
            warnings.append("No table in a supported layout was found; review the text and convert it to the "
                            + ("EOB" if kind == "eob" else "bill") + " CSV columns before checking")
    return result


def extract_request(payload):
    """Validate a /api/extract JSON body and extract the uploaded PDF in memory."""
    if not isinstance(payload, dict) or set(payload) != {"kind", "filename", "content_base64"}:
        raise PdfError(SCHEMA_ERROR)
    kind, filename, content = payload["kind"], payload["filename"], payload["content_base64"]
    if kind not in KINDS or not isinstance(filename, str) or not filename.strip() or len(filename) > 255 or not isinstance(content, str) or not content:
        raise PdfError(SCHEMA_ERROR)
    if content.startswith("data:") and "," in content[:100]:
        content = content.split(",", 1)[1]
    if len(content) > (MAX_PDF_BYTES * 4) // 3 + 1024:
        raise PdfError("PDF is larger than 11 MB")
    try:
        data = base64.b64decode(re.sub(r"\s", "", content), validate=True)
    except (binascii.Error, ValueError):
        raise PdfError(UNREADABLE_ERROR) from None
    return extract_upload(kind, filename, data)
