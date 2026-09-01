import os
import sys
import traceback
from urllib.parse import parse_qs

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
cwd = os.getcwd()

for p in [current_dir, parent_dir, cwd]:
    if p not in sys.path:
        sys.path.insert(0, p)

INIT_ERROR = None
fastapi_app = None

try:
    from backend.main import app as imported_app
    fastapi_app = imported_app
except Exception as e:
    INIT_ERROR = f"VERCEL MODULE IMPORT FAILURE:\n{str(e)}\n\nFULL STACK TRACEBACK:\n{traceback.format_exc()}"
    print(INIT_ERROR)

class VercelASGIAdapter:
    def __init__(self, inner_app):
        self.inner_app = inner_app

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http":
            if INIT_ERROR:
                await send({
                    "type": "http.response.start",
                    "status": 500,
                    "headers": [(b"content-type", b"text/plain; charset=utf-8")]
                })
                await send({
                    "type": "http.response.body",
                    "body": INIT_ERROR.encode("utf-8")
                })
                return

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

            try:
                await self.inner_app(scope, receive, send)
            except Exception as exc:
                err_text = f"VERCEL RUNTIME EXECUTION EXCEPTION:\n{str(exc)}\n\nFULL STACK TRACEBACK:\n{traceback.format_exc()}"
                await send({
                    "type": "http.response.start",
                    "status": 500,
                    "headers": [(b"content-type", b"text/plain; charset=utf-8")]
                })
                await send({
                    "type": "http.response.body",
                    "body": err_text.encode("utf-8")
                })
        else:
            if self.inner_app:
                await self.inner_app(scope, receive, send)

app = VercelASGIAdapter(fastapi_app)






