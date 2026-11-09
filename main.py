"""Compatibility entry point: uvicorn main:app still works from the project root."""
from backend.main import app  # noqa: F401
