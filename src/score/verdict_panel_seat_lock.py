"""One-scorer-per-seat lock for the verdict panel.

Held apart from ``verdict_panel`` because it is a filesystem concurrency
guard, not scoring logic: it knows nothing about judges or verdicts beyond
the path it protects. Everything here is a private detail of
``verdict_panel``, so nothing is package-exported.
"""

from __future__ import annotations

import os
from pathlib import Path

__all__: list[str] = []


class _SeatLock:
    """One scorer per (verdict file, level). Refuses rather than racing.

    Three separate incidents in this run came from two processes scoring the
    same seat: each reads its resume set once at start, so both decide the same
    responses are unscored and both write. Deduplicating afterwards recovers the
    data but not the wasted hours, and one of those races produced a stage 6
    result computed on a partial table. A lock beside the output file makes the
    second process fail loudly instead.
    """

    def __init__(self, verdicts_path, level: int) -> None:
        # The lock scopes to (file, level), deliberately not to the judge: two
        # judges writing the same verdicts file would race exactly like two
        # copies of one judge, so a per-judge lock would reintroduce the race.
        self.path = Path(f"{verdicts_path}.L{level}.lock")
        self.owned = False

    def __enter__(self):
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise RuntimeError(
                f"another scorer holds {self.path}; refusing to write the same "
                "verdicts twice. Remove the lock only if no scorer is running."
            ) from None
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        self.owned = True
        return self

    def __exit__(self, *exc) -> None:
        if self.owned:
            self.path.unlink(missing_ok=True)
