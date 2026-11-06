"""Local-only HTTP adapter. Not an Internet-facing production server."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json

from .domain import AppError, MAX_INPUT_BYTES, Product, parse_json
from .provider import DemoPlanner, OpenAIPlanner
from .render import generate


def make_handler(demo=False):
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def respond(self, status, value):
            raw = json.dumps(value, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            if self.path == "/health":
                self.respond(200, {"status": "ok", "mode": "demo" if demo else "live"})
            else:
                self.respond(404, {"error": {"code": "not_found", "message": "Используйте POST /generate."}})

        def do_POST(self):
            try:
                if self.path != "/generate":
                    raise AppError("not_found", "Используйте POST /generate.", 404)
                if self.headers.get("Transfer-Encoding"):
                    raise AppError("invalid_request", "Chunked-запросы не поддерживаются.", 400)
                if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                    raise AppError("unsupported_media_type", "Используйте Content-Type: application/json.", 415)
                try:
                    size = int(self.headers.get("Content-Length", ""))
                except ValueError:
                    raise AppError("invalid_request", "Нужен корректный Content-Length.", 411) from None
                if not 0 < size <= MAX_INPUT_BYTES:
                    raise AppError("input_too_large", "Ожидается JSON размером от 1 байта до 64 КБ.", 413)
                raw = self.rfile.read(size)
                if len(raw) != size:
                    raise AppError("invalid_request", "Тело запроса не завершено.", 400)
                product = Product.from_dict(parse_json(raw))
                planner = DemoPlanner() if demo else OpenAIPlanner()
                self.respond(200, generate(product, planner))
            except AppError as error:
                self.respond(error.status, {"error": {"code": error.code, "message": str(error)}})
            except TimeoutError:
                self.respond(408, {"error": {"code": "request_timeout", "message": "Истекло время чтения запроса."}})

        def log_message(self, fmt, *args):
            pass  # No product descriptions, keys or provider bodies in access logs.
    return Handler


def serve(port, demo):
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(demo))
    print(f"Cardcraft: http://127.0.0.1:{port} ({'demo' if demo else 'live'})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
