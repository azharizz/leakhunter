"""Private, durable intent records and a per-target controller lock (Linux/macOS)."""
from __future__ import annotations

from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile


class HandoffCanceled(RuntimeError):
    pass


class JournalAPI:
    def __init__(self, api, journal):
        self.api, self.journal = api, journal

    def request(self, method, path, body=None):
        self.journal.check_stop()
        return self.api.request(method, path, body)


class RunJournal:
    def __init__(self, directory, project, target, intent, configuration):
        self.directory = Path(directory)
        self.key = f"gitlab.com:{project}:{target}:{intent}"
        self.digest = hashlib.sha256(self.key.encode()).hexdigest()
        self.path = self.directory / (self.digest + ".json")
        self.lock_path = self.directory / (hashlib.sha256(f"{project}:{target}".encode()).hexdigest() + ".lock")
        self.configuration = configuration
        self.data = {}
        self.lock_fd = None

    def __enter__(self):
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        info = self.directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError("Controller state directory must be a private, operator-owned real directory (0700)")
        self.lock_fd = os.open(self.lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        try:
            self._private_file(self.lock_fd)
            fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if self.path.exists() or self.path.is_symlink():
                fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                try:
                    self._private_file(fd)
                except BaseException:
                    os.close(fd)
                    raise
                with os.fdopen(fd) as source:
                    text = source.read(65537)
                if len(text) > 65536:
                    raise ValueError("Controller state is unexpectedly large")
                self.data = json.loads(text)
                if (self.data.get("version") != 1 or self.data.get("key") != self.key
                        or self.data.get("configuration_sha256") != self.configuration):
                    raise ValueError("Stored intent has a different configuration; do not silently expand its scope")
            else:
                self.save("CREATED")
        except BaseException:
            os.close(self.lock_fd)
            self.lock_fd = None
            raise
        return self

    @staticmethod
    def _private_file(fd):
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_mode & 0o077 or info.st_nlink != 1):
            raise ValueError("Controller state and lock files must be private owned regular files without links")

    def check_stop(self):
        try:
            (self.directory / "STOP").lstat()
        except FileNotFoundError:
            return
        raise HandoffCanceled("Operator STOP flag is present; remote work may still continue")

    def save(self, state, **values):
        if state in {"READY_FOR_REVIEW", "DEPLOYED_AND_VERIFIED"}:
            self.check_stop()
        self.data.update(values)
        self.data.update(version=1, key=self.key, configuration_sha256=self.configuration,
                         state=state, updated_at=datetime.now(timezone.utc).isoformat())
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", dir=self.directory, delete=False) as output:
                temporary = output.name
                json.dump(self.data, output, sort_keys=True)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self.path)
            directory_fd = os.open(self.directory, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)

    def __exit__(self, error_type, error, traceback):
        try:
            if error_type:
                canceled = issubclass(error_type, (HandoffCanceled, KeyboardInterrupt))
                self.save("CANCELED" if canceled else "STOPPED", error_type=error_type.__name__)
        finally:
            os.close(self.lock_fd)
            self.lock_fd = None


def trigger_issue(start, journal):
    """Start the Duo session once per intent; an interrupted start is never repeated blindly."""
    journal.check_stop()
    if journal.data.get("dispatch_started"):
        if journal.data.get("duo_session_id"):
            return journal.data["duo_session_id"]
        raise RuntimeError("Duo start is uncertain. No duplicate was sent; check the project's agent sessions before recovery")
    journal.save("TRIGGER_INTENT", dispatch_started=True)
    journal.check_stop()
    session = start()
    journal.save("TRIGGERED", duo_session_id=session["id"])
    return session["id"]
