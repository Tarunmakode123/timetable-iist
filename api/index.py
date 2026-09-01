import os
import sys
from urllib.parse import parse_qs

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
cwd = os.getcwd()

for p in [current_dir, parent_dir, cwd]:
    if p not in sys.path:
        sys.path.insert(0, p)

from backend.main import app

class VercelPathFixMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http":
            query_string = scope.get("query_string", b"").decode("utf-8")
            parsed_query = parse_qs(query_string)
            if "path" in parsed_query and parsed_query["path"]:
                scope["path"] = parsed_query["path"][0]
            elif scope.get("path") in ["/api/index.py", "/api/index", "/api"]:
                headers = dict(scope.get("headers", []))
                matched_path = headers.get(b"x-matched-path", b"").decode("utf-8")
                if matched_path and matched_path not in ["/api/index.py", "/api/index", "/api"]:
                    scope["path"] = matched_path
        await self.app(scope, receive, send)

app.add_middleware(VercelPathFixMiddleware)




