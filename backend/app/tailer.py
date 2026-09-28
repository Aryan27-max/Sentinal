"""Follow a growing log file without holding it open.

Every poll: stat → open → seek(offset) → read → close. Not keeping a handle means the
generator can rename the file on Windows. Rotation is detected by a change of file identity
(st_ino), truncation by the size shrinking below our offset; both restart from offset 0.
A trailing partial line stays buffered until its newline arrives.
"""

import asyncio
import os
from collections.abc import AsyncIterator
from pathlib import Path


class Tailer:
    def __init__(self, path: Path, poll_ms: int = 200, from_start: bool = False) -> None:
        self.path = path
        self.poll_seconds = poll_ms / 1000
        self.offset = 0
        self.ino: int | None = None
        self.buffer = b""
        if not from_start:
            try:
                st = os.stat(path)
                self.offset, self.ino = st.st_size, st.st_ino
            except FileNotFoundError:
                pass

    def read_new_lines(self) -> list[str]:
        """Blocking read of everything appended since the last call. Run it in a thread."""
        try:
            st = os.stat(self.path)
        except FileNotFoundError:
            return []

        if self.ino is not None and st.st_ino != self.ino:  # rotated: a different file now
            self.offset, self.buffer = 0, b""
        self.ino = st.st_ino
        if st.st_size < self.offset:  # truncated
            self.offset, self.buffer = 0, b""
        if st.st_size == self.offset:
            return []

        with open(self.path, "rb") as f:
            f.seek(self.offset)
            data = f.read()
        self.offset += len(data)

        *lines, self.buffer = (self.buffer + data).split(b"\n")
        return [text for raw in lines if (text := raw.decode("utf-8", "replace").rstrip("\r"))]

    async def follow(self) -> AsyncIterator[list[str]]:
        while True:
            lines = await asyncio.to_thread(self.read_new_lines)
            if lines:
                yield lines
            await asyncio.sleep(self.poll_seconds)
