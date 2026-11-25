"""Explicit Vercel ASGI entrypoint for the FastAPI application.

Vercel detects index.py at the backend project root. Keeping the exported
application here avoids ambiguity when the Vercel project Root Directory is
set to `backend`. The normal local command remains `uvicorn app.main:app`.
"""

from app.main import app

__all__ = ["app"]
