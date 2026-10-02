from __future__ import annotations

import io
import os
from typing import IO

from ._types import FileContent, FileInput

_CONTENT_TYPES = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "doc": "application/msword",
    "txt": "text/plain",
    "pdf": "application/pdf",
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "ogg": "audio/ogg",
    "m4a": "audio/mp4",
    "webm": "audio/webm",
}

UploadPart = tuple[str, IO[bytes], str]


class Upload:
    """A file for the multipart body that can be sent again on every retry.

    Paths are opened per attempt and streamed from disk. Open files are sent
    whole, from the beginning, on every attempt.
    """

    def __init__(self, file: FileInput) -> None:
        self._path: str | None = None
        self._stream: IO[bytes] | None = None
        self._opened: IO[bytes] | None = None

        if isinstance(file, (str, os.PathLike)):
            self._path = os.fspath(file)
            self.file_name = os.path.basename(self._path)
            self.content_type = content_type_for(self.file_name)
            return

        if isinstance(file, tuple):
            self.file_name = file[0]
            content: FileContent = file[1]
            self.content_type = file[2] if len(file) == 3 else content_type_for(self.file_name)
        elif isinstance(file, bytes):
            raise TypeError("Raw bytes have no file name; pass (file_name, data) instead")
        else:
            name = getattr(file, "name", None)
            if not isinstance(name, str) or not name:
                raise TypeError("The file object has no name; pass (file_name, file) instead")
            self.file_name = os.path.basename(name)
            self.content_type = content_type_for(self.file_name)
            content = file

        if isinstance(content, bytes):
            self._stream = io.BytesIO(content)
        elif content.seekable():
            self._stream = content
        else:
            # A stream that cannot be rewound would break retries; keep it in memory.
            self._stream = io.BytesIO(content.read())

    def part(self) -> UploadPart:
        """The ``(file_name, file, content_type)`` tuple for the next attempt."""
        if self._path is not None:
            self.close()
            self._opened = open(self._path, "rb")  # noqa: SIM115 - closed by close()
            return (self.file_name, self._opened, self.content_type)
        assert self._stream is not None
        self._stream.seek(0)
        return (self.file_name, self._stream, self.content_type)

    def close(self) -> None:
        """Closes a file this object opened itself; caller-owned files stay open."""
        if self._opened is not None:
            self._opened.close()
            self._opened = None


def content_type_for(file_name: str) -> str:
    extension = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
    return _CONTENT_TYPES.get(extension, "application/octet-stream")
