from typing import Protocol


class JsonSocket(Protocol):
    async def send_json(self, data: dict) -> None:
        ...


class JobWebSocketTransport:
    def __init__(self) -> None:
        self._connections: dict[str, list[JsonSocket]] = {}

    def register(self, job_id: str, websocket: JsonSocket) -> None:
        self._connections.setdefault(job_id, []).append(websocket)

    def unregister(self, job_id: str, websocket: JsonSocket) -> None:
        self._connections[job_id] = [
            conn for conn in self._connections.get(job_id, []) if conn is not websocket
        ]

    async def broadcast(self, job_id: str, message: dict) -> None:
        connections = self._connections.get(job_id, [])
        if not connections:
            return

        closed: list[JsonSocket] = []
        for websocket in list(connections):
            try:
                await websocket.send_json(message)
            except Exception:
                closed.append(websocket)

        if closed:
            self._connections[job_id] = [
                conn for conn in connections if conn not in closed
            ]


def build_job_snapshot(job: dict) -> dict:
    return {
        "id": job["id"],
        "status": job["status"],
        "step": job.get("step"),
        "step_status": job.get("step_status"),
        "progress": job.get("progress", 0),
        "error": job.get("error"),
        "transcript": job.get("transcript") if job["status"] == "done" else None,
    }
