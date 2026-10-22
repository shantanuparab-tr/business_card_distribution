"""Non-blocking Enter-key detection.

A daemon thread blocks on stdin and pushes the monotonic time of every Enter
press into a queue, so the control loops never stall waiting for input.
"""

import queue
import sys
import threading
import time


class EnterListener:
    def __init__(self) -> None:
        self.presses: queue.Queue[float] = queue.Queue()
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        for _ in sys.stdin:
            self.presses.put(time.monotonic())

    def poll(self) -> float | None:
        """Return the timestamp of the oldest unread press, or None."""
        try:
            return self.presses.get_nowait()
        except queue.Empty:
            return None

    def drain(self) -> int:
        """Discard all unread presses and return how many there were."""
        count = 0
        while self.poll() is not None:
            count += 1
        return count
