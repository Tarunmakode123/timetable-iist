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

from backend.main import app as fastapi_app

async def app(scope, receive, send):
    if scope.get("type") == "http":
        # Extract query parameters directly from ASGI raw query_string
        query_string = scope.get("query_string", b"").decode("utf-8")
        parsed_query = parse_qs(query_string)
        if "path" in parsed_query and parsed_query["path"]:
            scope["path"] = parsed_query["path"][0]
        elif scope.get("path") in ["/api/index.py", "/api/index", "/api"]:
            headers = dict(scope.get("headers", []))
            matched_path = headers.get(b"x-matched-path", b"").decode("utf-8")
            if matched_path and matched_path not in ["/api/index.py", "/api/index"]:
                scope["path"] = matched_path

    try:
        await fastapi_app(scope, receive, send)
    except Exception as e:
        err_trace = f"Vercel ASGI Execution Crash:\n{str(e)}\n\nTraceback:\n{traceback.format_exc()}"
        if scope.get("type") == "http":
            await send({
                "type": "http.response.start",
                "status": 500,
                "headers": [(b"content-type", b"text/plain; charset=utf-8")]
            })
            await send({
                "type": "http.response.body",
                "body": err_trace.encode("utf-8")
            })



