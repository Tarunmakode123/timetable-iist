import os
import sys
import traceback

# Add the project root directory to sys.path so Vercel can locate the backend package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
