"""Sample server and resumable background analysis. Uploads stay in memory."""

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .models import ModelError, case_from_dict, to_dict
from .repository import demo_inputs, list_cases, list_demos, load_case, sample_inputs
from .service import analyze, analyze_policy_text, check_documents

STATIC = Path(__file__).parent / "static"
MAX_BODY = 15 * 1024 * 1024  # base64 JSON of an ~11 MB PDF; text endpoints share the limit
LEGACY_WAIT_SECONDS = 0.1
HEALTH_PATHS = {"/ping", "/health", "/healthz", "/ready", "/readyz", "/livez"}


class Server(ThreadingHTTPServer):
    # The stdlib default listen backlog is only five on deployed Python 3.12.
    # Polls/uploads must not crowd a simultaneous load-balancer health probe out.
    request_queue_size = 128
    daemon_threads = True


def execute(path, payload, *, cached=False):
    """Shared worker/legacy API boundary; the browser uses background jobs."""
    if path == "/api/extract":
        from .documents_pdf import extract_request
        return extract_request(payload)
    if path == "/api/case":
        case, documents = load_case(payload["id"])
        result = analyze_policy_text(case, documents["policy"], case.id + "/policy.md")
        result["documents"] = documents
        return result
    if path == "/api/check":
        if not isinstance(payload, dict):
            raise ModelError("Expected a JSON object")
        compilation = None
        if "compilation" in payload or "compilation_receipt" in payload:
            from .compilation_receipts import verify
            if not isinstance(payload.get("policy"), str):
                raise ModelError("Policy text is required")
            compilation = verify(payload.get("compilation"), payload.get("compilation_receipt"), payload["policy"])
        return check_documents(payload, compilation=compilation)
    if path == "/api/compile":
        if not isinstance(payload, dict) or set(payload) - {"document", "document_id", "case", "provider"}:
            raise ModelError("Expected document, optional document_id, provider and case")
        document = payload.get("document")
        document_id = payload.get("document_id", "uploaded-policy")
        if not isinstance(document, str) or not document.strip() or not isinstance(document_id, str) or not 0 < len(document_id.strip()) <= 200:
            raise ModelError("Nonempty policy document and document_id (up to 200 characters) are required")
        if "case" in payload:
            return analyze_policy_text(case_from_dict(payload["case"]), document, document_id)
        from .compiler import get_compiler
        from .compilation_receipts import sign
        compiler = get_compiler(payload.get("provider"))
        if cached:
            from .jobs import COMPILED
            compilation = COMPILED.compile(document, document_id, compiler).as_dict()
        else:
            compilation = compiler.compile(document, document_id).as_dict()
        return {"compilation": compilation, "compilation_receipt": sign(compilation)}
    case = case_from_dict(payload)
    return {"case": to_dict(case), "documents": {}, "report": analyze(case)}


def error_kind(exc):
    """'provider' when an LLM backend failed (nothing was substituted); otherwise 'input'."""
    from .providers import ProviderError
    return "provider" if isinstance(exc, ProviderError) else "input"


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def handle_one_request(self):
        started = time.monotonic()
        self._response_status = None
        try:
            super().handle_one_request()
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            # A disconnected/slow client must not produce an HTTP 5xx traceback.
            pass
        finally:
            if self._response_status is not None:
                path = urlsplit(getattr(self, "path", "/")).path
                for prefix in ("/api/jobs/", "/api/cases/", "/api/samples/", "/api/demos/"):
                    if path.startswith(prefix):
                        path = prefix + ":id"
                        break
                print(json.dumps({"method": getattr(self, "command", "?"), "path": path,
                                  "status": self._response_status,
                                  "ms": round((time.monotonic() - started) * 1000, 2)}), flush=True)

    def send_response(self, code, message=None):
        self._response_status = code
        super().send_response(code, message)

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
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_HEAD(self):
        return self.do_GET()

    def __getattr__(self, name):
        # BaseHTTPRequestHandler otherwise emits 501 for unsupported methods.
        if name.startswith("do_"):
            return lambda: self.reply(405, {"error": "Use GET or POST for this endpoint"})
        raise AttributeError(name)

    def legacy_analysis(self, operation, payload):
        """Preserve fast API responses; hand slow callers a job within 100ms."""
        from .jobs import JOBS
        store = getattr(self.server, "job_store", JOBS)
        status, body = store.poll({"operation": operation, "payload": payload}, execute, wait_seconds=LEGACY_WAIT_SECONDS)
        if body.get("status") in ("done", "failed"):
            with store.lock:
                store.jobs.pop(body["job_id"], None)
            if body["status"] == "done":
                return self.reply(200, body["result"])
            return self.reply(400, {"error": body["error"], "kind": body["kind"]})
        return self.reply(status, body)

    def do_GET(self):
        path = urlsplit(self.path).path
        try:
            if path in HEALTH_PATHS:
                return self.reply(200, {"ok": True})
            if path.startswith("/api/jobs/"):
                from .jobs import JOBS
                status, body = getattr(self.server, "job_store", JOBS).status(path.removeprefix("/api/jobs/"))
                return self.reply(status, body)
            if path == "/api/jobs":
                return self.reply(200, {"ok": True, "message": "POST an operation and payload to start a check"})
            if path == "/favicon.ico":
                return self.reply(204, b"", "image/x-icon")
            if path == "/api/demos":
                return self.reply(200, list_demos())
            if path.startswith("/api/demos/"):
                return self.reply(200, demo_inputs(path.removeprefix("/api/demos/")))
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
                case_id = path.removeprefix("/api/cases/")
                load_case(case_id)  # Validate the catalog ID before starting work.
                return self.legacy_analysis("/api/case", {"id": case_id})
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
        is_job = path == "/api/jobs" or path.startswith("/api/jobs/")
        if not is_job and path not in ("/api/analyze", "/api/compile", "/api/check", "/api/extract"):
            return self.reply(404, {"error": "Not found"})
        # Reject cross-origin browser requests; this endpoint has no CORS opt-in.
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            return self.reply(403, {"error": "Cross-site requests are not supported"})
        try:
            if len(self.headers.get_all("Content-Length", [])) != 1:
                return self.reply(400, {"error": "Send one Content-Length header", "kind": "input"})
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                return self.reply(400, {"error": "Send a nonempty JSON object", "kind": "input"})
            if length > MAX_BODY:
                return self.reply(413, {"error": "Request body must be between 1 byte and 15 MiB"})
            if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
                return self.reply(400 if is_job else 415, {"error": "Send application/json", "kind": "input"})
            if self.headers.get("Transfer-Encoding"):
                return self.reply(400, {"error": "Send JSON with a Content-Length", "kind": "input"})
            payload = json.loads(self.rfile.read(length))
            if is_job:
                from .jobs import JOBS
                store = getattr(self.server, "job_store", JOBS)
                status, result = store.poll(payload, lambda op, data: execute(op, data, cached=True),
                                           None if path == "/api/jobs" else path.removeprefix("/api/jobs/"))
                return self.reply(status, result)
            return self.legacy_analysis(path, payload)
        except (ModelError, ValueError, TypeError, RecursionError) as exc:
            return self.reply(400, {"error": str(exc), "kind": error_kind(exc)})
        except (TimeoutError, OSError):
            return self.reply(400, {"error": "The upload was interrupted. Please try again.", "kind": "input"})


def main():
    parser = argparse.ArgumentParser(description="Fineprint offline case explorer")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    args = parser.parse_args()
    server = Server((args.host, args.port), Handler)
    print(f"Fineprint: http://{args.host}:{server.server_port} (Ctrl+C to stop)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
