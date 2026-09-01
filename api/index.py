import os
import sys
import traceback
from fastapi.responses import PlainTextResponse

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
cwd = os.getcwd()

for p in [current_dir, parent_dir, cwd]:
    if p not in sys.path:
        sys.path.insert(0, p)

from backend.main import app

@app.middleware("http")
async def vercel_path_fix_middleware(request, call_next):
    # Adjust path if rewritten to /api/index.py
    custom_path = request.query_params.get("path")
    if custom_path:
        request.scope["path"] = custom_path
    elif request.scope["path"] in ["/api/index.py", "/api/index", "/api"]:
        matched_path = request.headers.get("x-matched-path") or request.headers.get("x-forwarded-uri")
        if matched_path and matched_path not in ["/api/index.py", "/api/index"]:
            request.scope["path"] = matched_path

    try:
        return await call_next(request)
    except Exception as e:
        err_msg = f"Vercel Server Exception on {request.method} {request.url.path}:\n{str(e)}\n\nTraceback:\n{traceback.format_exc()}"
        return PlainTextResponse(err_msg, status_code=500)


