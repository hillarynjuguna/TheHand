from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: bytes
    stderr: bytes


class AsyncCommandRunner:
    async def run(self, command: Sequence[str]) -> CommandResult:
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            executable = command[0] if command else "<empty command>"
            raise FileNotFoundError(
                f"Required runtime executable was not found: {executable}. "
                "Install it or configure the matching provider path before starting a job."
            ) from exc
        stdout, stderr = await process.communicate()
        return CommandResult(process.returncode, stdout, stderr)
