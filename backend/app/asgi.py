"""ASGI entrypoint for uvicorn on Cloud Run."""

from app.main import create_app

app = create_app()  # pragma: no cover
