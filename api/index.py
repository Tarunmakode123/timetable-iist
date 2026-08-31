import os
import sys

# Add the project root directory to sys.path so Vercel can locate the backend package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.main import app
