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
async def catch_exceptions_middleware(request, call_next):
    try:
        return await call_next(request)
    except Exception as e:
        err_msg = f"Vercel Server Exception on {request.method} {request.url.path}:\n{str(e)}\n\nTraceback:\n{traceback.format_exc()}"
        return PlainTextResponse(err_msg, status_code=500)


