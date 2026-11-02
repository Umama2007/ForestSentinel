"""
Vercel Serverless Function entrypoint for ForestSentinel Web Dashboard.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add the project root directory to sys.path so modules and templates are accessible
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import app

# Export the WSGI app for Vercel
app = app
