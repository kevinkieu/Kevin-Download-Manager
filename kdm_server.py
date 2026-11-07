"""
KDM - Kevin Download Manager
Local Bridge Server: Connects Browser Extensions (Chrome, Cốc Cốc, Edge, Firefox) with KDM Desktop App
"""

import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Callable, Optional, Dict, Any


class KDMRequestHandler(BaseHTTPRequestHandler):
    server: 'KDMServer'

    def _set_cors_headers(self, status: int = 200, content_type: str = "application/json"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")
        self.end_headers()

    def do_OPTIONS(self):
        self._set_cors_headers(204)

    def do_GET(self):
        path = self.path.split("?")[0]

        if path in ("/status", "/health"):
            exts = ""
            if self.server.settings:
                exts = self.server.settings.get("intercept_extensions", "")
            self._set_cors_headers(200)
            self.wfile.write(json.dumps({
                "status": "ok",
                "name": "Kevin Download Manager",
                "short_name": "KDM",
                "version": "1.2.0",
                "intercept_extensions": exts
            }).encode("utf-8"))
            return

        if path in ("/settings", "/config"):
            exts = ""
            if self.server.settings:
                exts = self.server.settings.get("intercept_extensions", "")
            self._set_cors_headers(200)
            self.wfile.write(json.dumps({
                "intercept_extensions": exts
            }).encode("utf-8"))
            return

        if path == "/tasks":
            tasks = []
            if self.server.engine:
                with self.server.engine.lock:
                    tasks = [t.to_dict() for t in self.server.engine.tasks.values()]
            self._set_cors_headers(200)
            self.wfile.write(json.dumps({"tasks": tasks}).encode("utf-8"))
            return

        self._set_cors_headers(404)
        self.wfile.write(json.dumps({"error": "Not Found"}).encode("utf-8"))

    def do_POST(self):
        path = self.path.split("?")[0]
        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"

        try:
            data = json.loads(body)
        except Exception:
            data = {}

        if path == "/download":
            url = data.get("url")
            filename = data.get("filename")
            is_video = data.get("is_video", False)
            format_id = data.get("format_id")
            start_now = data.get("start_now", True)

            if not url:
                self._set_cors_headers(400)
                self.wfile.write(json.dumps({"error": "Missing URL"}).encode("utf-8"))
                return

            if self.server.on_new_download:
                # Trigger callback for GUI or automatic queue
                res = self.server.on_new_download(url=url, filename=filename, is_video=is_video,
                                                   format_id=format_id, start_now=start_now,
                                                   metadata=data)
                self._set_cors_headers(200)
                self.wfile.write(json.dumps({"success": True, "result": res}).encode("utf-8"))
            else:
                self._set_cors_headers(500)
                self.wfile.write(json.dumps({"error": "No handler attached"}).encode("utf-8"))
            return

        if path == "/video_info":
            url = data.get("url")
            if not url:
                self._set_cors_headers(400)
                self.wfile.write(json.dumps({"error": "Missing URL"}).encode("utf-8"))
                return

            try:
                from kdm_engine import KDMEngine
                info = KDMEngine.extract_video_info(url)
                self._set_cors_headers(200)
                self.wfile.write(json.dumps({"success": True, "info": info}).encode("utf-8"))
            except Exception as e:
                self._set_cors_headers(500)
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            return

        self._set_cors_headers(404)
        self.wfile.write(json.dumps({"error": "Endpoint Not Found"}).encode("utf-8"))

    def log_message(self, format, *args):
        # Mute console logging to keep terminal tidy
        pass


class KDMServer(HTTPServer):
    def __init__(self, host: str = "127.0.0.1", port: int = 59123, engine=None, settings=None):
        super().__init__((host, port), KDMRequestHandler)
        self.engine = engine
        self.settings = settings
        self.on_new_download: Optional[Callable[..., Any]] = None
        self._thread: Optional[threading.Thread] = None

    def start_background(self):
        self._thread = threading.Thread(target=self.serve_forever, daemon=True)
        self._thread.start()

    def stop(self):
        self.shutdown()
        self.server_close()
