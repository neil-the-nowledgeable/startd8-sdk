"""Live-follow for an in-progress kickoff-panel transcript (FR-UX-17/18/19).

The orchestrator writes the transcript **round-by-round** to a single, atomically-replaced
document (``_persist`` → ``safe_write`` tmp + ``os.replace``), so following it needs **no
server** — poll the file signature (mtime + size), and on change re-read + re-render (re-read
is ``$0``, FR-UX-2). The atomic replace guarantees a poll never sees a torn write (FR-UX-19):
each read is either the previous or the next *complete* document.

:class:`TranscriptWatcher` separates the change-detection (``poll``) from the loop (``follow``)
so the diff logic is unit-testable without real sleeping, and the loop terminates on its own
when the run reaches a terminal status (``completed`` / ``halted``).
"""

from __future__ import annotations

import time
from typing import Callable, Optional

from .models import KickoffTranscript
from .store import KickoffPanelStore


class TranscriptWatcher:
    """Poll a transcript file and yield it when its on-disk signature changes."""

    def __init__(
        self,
        store: KickoffPanelStore,
        session_id: str,
        *,
        interval: float = 1.0,
    ) -> None:
        self.store = store
        self.session_id = session_id
        self.interval = interval
        self._last_sig: Optional[tuple[float, int]] = None

    def _signature(self) -> Optional[tuple[float, int]]:
        """(mtime, size) of the transcript file, or ``None`` if it isn't there yet."""
        try:
            st = self.store._path(self.session_id).stat()
        except FileNotFoundError:
            return None
        return (st.st_mtime, st.st_size)

    def poll(self) -> Optional[KickoffTranscript]:
        """Return the transcript **iff** its signature changed since the last poll.

        Returns ``None`` when unchanged, still absent, or momentarily unreadable (a decode
        error is treated as "no change" so a transient mid-write blip never crashes the
        follow loop — the next poll picks up the settled document).
        """
        sig = self._signature()
        if sig is None or sig == self._last_sig:
            return None
        try:
            transcript = self.store.load(self.session_id)
        except (FileNotFoundError, ValueError):
            return None  # vanished or not-yet-valid JSON — retry next tick
        self._last_sig = sig
        return transcript

    def follow(
        self,
        on_change: Callable[[KickoffTranscript], None],
        *,
        sleep: Callable[[float], None] = time.sleep,
        max_ticks: Optional[int] = None,
    ) -> Optional[KickoffTranscript]:
        """Call ``on_change`` on every change until the run is done (or ``max_ticks``).

        Renders immediately if the transcript already exists, then polls every ``interval``
        seconds. Stops — returning the last transcript — as soon as one is ``is_done``
        (terminal status), so a completed/halted run renders once and exits without spinning.
        ``sleep`` and ``max_ticks`` are injectable for tests. ``KeyboardInterrupt`` propagates
        to the caller (the CLI turns it into a clean stop).
        """
        last: Optional[KickoffTranscript] = None
        ticks = 0
        while True:
            transcript = self.poll()
            if transcript is not None:
                last = transcript
                on_change(transcript)
                if transcript.is_done:
                    return transcript
            ticks += 1
            if max_ticks is not None and ticks >= max_ticks:
                return last
            sleep(self.interval)
