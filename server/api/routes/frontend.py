from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles


def register_frontend_routes(app: FastAPI, frontend_dir: str) -> None:
    frontend_path = Path(frontend_dir)

    if frontend_path.exists():
        app.mount("/assets", StaticFiles(directory=str(frontend_path / "assets")), name="assets")

        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            if full_path.startswith("api/") or full_path.startswith("ws/"):
                raise HTTPException(status_code=404)
            index = frontend_path / "index.html"
            if index.exists():
                return FileResponse(str(index))
            return JSONResponse(
                {"message": "TheHand server is running. Build the frontend and place dist/ next to main.py."},
                status_code=200,
            )
    else:
        @app.get("/")
        async def no_frontend():
            return JSONResponse({
                "message": "TheHand API is running. Frontend not found.",
                "hint": "Run `npm run build` in the TheHand repo and copy dist/ next to main.py",
                "api_docs": "/docs",
            })
