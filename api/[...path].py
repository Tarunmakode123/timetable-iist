import os
import sys
import traceback

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
cwd = os.getcwd()

for p in [current_dir, parent_dir, cwd]:
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from backend.main import app
except Exception as e:
    error_traceback = traceback.format_exc()
    
    # Fallback ASGI application to output traceback directly to the browser
    async def app(scope, receive, send):
        if scope['type'] == 'http':
            await send({
                'type': 'http.response.start',
                'status': 500,
                'headers': [
                    (b'content-type', b'text/plain; charset=utf-8'),
                ]
            })
            await send({
                'type': 'http.response.body',
                'body': f"Vercel Import Crash Traceback:\n\n{error_traceback}".encode('utf-8'),
            })
