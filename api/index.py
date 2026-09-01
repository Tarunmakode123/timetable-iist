import os
import sys
from urllib.parse import parse_qs

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
cwd = os.getcwd()

for p in [current_dir, parent_dir, cwd]:
    if p not in sys.path:
        sys.path.insert(0, p)

from backend.main import app as fastapi_app

class VercelASGIAdapter:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http":
            headers = dict(scope.get("headers", []))
            forwarded_uri = headers.get(b"x-forwarded-uri", b"").decode("utf-8")
            if forwarded_uri and forwarded_uri.startswith("/api"):
                scope["path"] = forwarded_uri.split("?")[0]
            else:
                raw_query = scope.get("query_string", b"").decode("utf-8")
                if "path=" in raw_query:
                    pq = parse_qs(raw_query)
                    if "path" in pq:
                        scope["path"] = pq["path"][0]

        await self.app(scope, receive, send)

app = VercelASGIAdapter(fastapi_app)





