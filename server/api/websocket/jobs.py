from __future__ import annotations

import asyncio
from collections.abc import MutableMapping

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from runtime.state import JOB_TERMINAL_STATUSES
from runtime.transport import JobWebSocketTransport, build_job_snapshot


def register_job_websocket_routes(app: FastAPI, jobs: MutableMapping[str, dict], job_transport: JobWebSocketTransport) -> None:
    @app.websocket("/ws/job/{job_id}")
    async def job_progress_ws(websocket: WebSocket, job_id: str):
        """
        Connect to get real-time job updates pushed over WebSocket.
        Sends JSON messages: {"status", "step", "progress", "transcript", "error"}.
        Closes automatically when job is done or errors.
        """
        await websocket.accept()
        job_transport.register(job_id, websocket)
        try:
            while True:
                if job_id not in jobs:
                    await websocket.send_json({"error": "job not found"})
                    break

                job = jobs[job_id]
                await websocket.send_json(build_job_snapshot(job))

                if job["status"] in JOB_TERMINAL_STATUSES:
                    break

                await asyncio.sleep(0.5)

        except WebSocketDisconnect:
            pass
        finally:
            try:
                job_transport.unregister(job_id, websocket)
            except Exception:
                pass
            try:
                await websocket.close()
            except Exception:
                pass
