"""Read-only sample server plus stateless JSON analysis. Uploads are processed in memory, never stored."""

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .models import ModelError, case_from_dict, to_dict
from .repository import list_cases, load_case, sample_inputs
from .service import analyze, analyze_policy_text, check_documents

STATIC = Path(__file__).parent / "static"
MAX_BODY = 15 * 1024 * 1024  # base64 JSON of an ~11 MB PDF; text endpoints share the limit


def error_kind(exc):
    """'provider' when an LLM backend failed (nothing was substituted); otherwise 'input'."""
    from .providers import ProviderError
    return "provider" if isinstance(exc, ProviderError) else "input"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Avoid putting case contents or identifiers into application logs.
        pass

    def reply(self, status, body, content_type="application/json; charset=utf-8"):
        if content_type.startswith("application/json"):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlsplit(self.path).path
        try:
            if path == "/ping":
                return self.reply(200, {"ok": True})
            if path == "/api/cases":
                return self.reply(200, list_cases())
            if path == "/api/status":
                from .compiler import default_provider
                name = default_provider()
                return self.reply(200, {"provider": name, "offline": name == "fallback"})
            if path == "/api/samples":
                return self.reply(200, list_cases())
            if path.startswith("/api/samples/"):
                return self.reply(200, sample_inputs(path.removeprefix("/api/samples/")))
            if path == "/api/evaluation":
                from .compiler import FallbackCompiler
                from .eval import run_evaluation
                return self.reply(200, run_evaluation(FallbackCompiler()))
            if path.startswith("/api/cases/"):
                case, documents = load_case(path.removeprefix("/api/cases/"))
                result = analyze_policy_text(case, documents["policy"], case.id + "/policy.md")
                result["documents"] = documents
                return self.reply(200, result)
            files = {"/": ("index.html", "text/html; charset=utf-8"),
                     "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                     "/styles.css": ("styles.css", "text/css; charset=utf-8")}
            if path in files:
                filename, content_type = files[path]
                return self.reply(200, (STATIC / filename).read_bytes(), content_type)
            return self.reply(404, {"error": "Not found"})
        except FileNotFoundError:
            return self.reply(404, {"error": "Unknown case"})
        except (ModelError, ValueError, TypeError) as exc:
            return self.reply(400, {"error": str(exc), "kind": error_kind(exc)})

    def do_POST(self):
        path = urlsplit(self.path).path
        if path not in ("/api/analyze", "/api/compile", "/api/check", "/api/extract"):
            return self.reply(404, {"error": "Not found"})
        # Reject cross-origin browser requests; this endpoint has no CORS opt-in.
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            return self.reply(403, {"error": "Cross-site requests are not supported"})
        if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
            return self.reply(415, {"error": "Send application/json"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_BODY:
                return self.reply(413, {"error": "Request body must be between 1 byte and 15 MiB"})
            payload = json.loads(self.rfile.read(length))
            if path == "/api/extract":
                from .documents_pdf import extract_request
                return self.reply(200, extract_request(payload))
            if path == "/api/check":
                return self.reply(200, check_documents(payload))
            if path == "/api/compile":
                if not isinstance(payload, dict) or set(payload) - {"document", "document_id", "case"}:
                    raise ModelError("Expected document, optional document_id and optional case")
                document = payload.get("document")
                document_id = payload.get("document_id", "uploaded-policy")
                if not isinstance(document, str) or not document.strip() or not isinstance(document_id, str) or not 0 < len(document_id.strip()) <= 200:
                    raise ModelError("Nonempty policy document and document_id (up to 200 characters) are required")
                if "case" in payload:
                    return self.reply(200, analyze_policy_text(case_from_dict(payload["case"]), document, document_id))
                from .compiler import get_compiler
                return self.reply(200, {"compilation": get_compiler().compile(document, document_id).as_dict()})
            case = case_from_dict(payload)
            return self.reply(200, {"case": to_dict(case), "documents": {}, "report": analyze(case)})
        except (ModelError, ValueError, TypeError, RecursionError) as exc:
            return self.reply(400, {"error": str(exc), "kind": error_kind(exc)})


def main():
    parser = argparse.ArgumentParser(description="Fineprint offline case explorer")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Fineprint: http://{args.host}:{server.server_port} (Ctrl+C to stop)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
