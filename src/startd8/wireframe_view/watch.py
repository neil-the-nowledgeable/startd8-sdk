"""EC-3: live-follow the wireframe manifests (mirrors the ``kickoff_view`` watch seam, Mottainai).

The wireframe preview is a pure function of a fixed set of manifest files (``schema.prisma``,
``pages.yaml``, …). Following them needs **no server** — poll the combined on-disk signature
(each file's mtime + size) and, on change, re-build the plan + re-render the file; an open browser
picks it up via the injected meta-refresh (``view._inject_live``).

:class:`ManifestWatcher` separates change-detection (``poll``) from the loop (``follow``) so the
diff logic is unit-testable without real sleeping (``sleep`` / ``max_ticks`` are injectable).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Iterable, Optional, Tuple

Signature = Tuple[Tuple[str, float, int], ...]


class ManifestWatcher:
    """Poll a set of files and fire a callback whenever their combined signature changes."""

    def __init__(
        self,
        paths_fn: Callable[[], Iterable[Path]],
        *,
        interval: float = 1.0,
    ) -> None:
        # ``paths_fn`` is re-evaluated each poll so a manifest that appears *later* starts being
        # watched (a not-yet-created pages.yaml added mid-session is picked up on its next tick).
        self.paths_fn = paths_fn
        self.interval = interval
        self._last_sig: Optional[Signature] = None

    def _signature(self) -> Signature:
        """(path, mtime, size) for every currently-existing watched file, order-stable."""
        sig = []
        for p in self.paths_fn():
            try:
                st = Path(p).stat()
            except OSError:
                continue  # absent / unreadable → simply not part of the signature yet
            sig.append((str(p), st.st_mtime, st.st_size))
        return tuple(sorted(sig))

    def poll(self) -> bool:
        """True iff the signature changed since the last poll (and updates the baseline)."""
        sig = self._signature()
        if sig == self._last_sig:
            return False
        self._last_sig = sig
        return True

    def follow(
        self,
        on_change: Callable[[], None],
        *,
        sleep: Callable[[float], None] = time.sleep,
        max_ticks: Optional[int] = None,
    ) -> None:
        """Call ``on_change`` on the first tick and on every subsequent change, forever.

        Renders immediately (the first ``poll`` always reports a change from ``None``), then polls
        every ``interval`` seconds. ``sleep`` / ``max_ticks`` are injectable for tests;
        ``KeyboardInterrupt`` propagates to the caller (the CLI turns it into a clean stop).
        """
        ticks = 0
        while True:
            if self.poll():
                on_change()
            ticks += 1
            if max_ticks is not None and ticks >= max_ticks:
                return
            sleep(self.interval)
