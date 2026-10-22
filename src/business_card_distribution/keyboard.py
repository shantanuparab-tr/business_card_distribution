"""Non-blocking Enter-key detection, from a terminal or straight from keyboards.

Listeners push the monotonic time of every Enter press into a queue, so the
control loops never stall waiting for input.

- ``StdinEnterListener`` reads lines from the terminal (interactive use).
- ``EvdevEnterListener`` reads key events from every keyboard under
  /dev/input, so it works headless (as a systemd service, with no terminal).
  The process needs read access to /dev/input/event*, i.e. the ``input`` group.
  Keyboards plugged in after start-up are picked up within a few seconds.
"""

import logging
import queue
import sys
import threading
import time

log = logging.getLogger(__name__)


class EnterListener:
    def __init__(self) -> None:
        self.presses: queue.Queue[float] = queue.Queue()

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


class StdinEnterListener(EnterListener):
    def __init__(self) -> None:
        super().__init__()
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        for _ in sys.stdin:
            self.presses.put(time.monotonic())


class EvdevEnterListener(EnterListener):
    RESCAN_PERIOD_S = 3.0

    def __init__(self) -> None:
        super().__init__()
        import evdev  # Linux-only; imported here so stdin mode works without it.

        self._evdev = evdev
        self._open_paths: set[str] = set()
        self._lock = threading.Lock()
        threading.Thread(target=self._scan_forever, daemon=True).start()

    def _scan_forever(self) -> None:
        enter_keys = {self._evdev.ecodes.KEY_ENTER, self._evdev.ecodes.KEY_KPENTER}
        warned_empty = False
        while True:
            for path in self._evdev.list_devices():
                with self._lock:
                    if path in self._open_paths:
                        continue
                try:
                    device = self._evdev.InputDevice(path)
                except OSError as e:  # unplugged mid-scan, or no permission
                    log.debug("cannot open %s: %s", path, e)
                    continue
                keys = device.capabilities().get(self._evdev.ecodes.EV_KEY, [])
                if not enter_keys & set(keys):
                    device.close()
                    continue
                with self._lock:
                    self._open_paths.add(path)
                log.info("listening for Enter on %s (%s)", device.name, path)
                threading.Thread(target=self._read, args=(device, enter_keys), daemon=True).start()
            with self._lock:
                if not self._open_paths and not warned_empty:
                    log.warning("no keyboard found yet (is the process in the 'input' group?)")
                    warned_empty = True
                elif self._open_paths:
                    warned_empty = False
            time.sleep(self.RESCAN_PERIOD_S)

    def _read(self, device, enter_keys: set[int]) -> None:
        try:
            for event in device.read_loop():
                # value 1 = key down; ignore 0 (up) and 2 (auto-repeat while held).
                if event.type == self._evdev.ecodes.EV_KEY and event.code in enter_keys and event.value == 1:
                    self.presses.put(time.monotonic())
        except OSError:
            log.info("keyboard %s disconnected", device.path)
        finally:
            with self._lock:
                self._open_paths.discard(device.path)
            device.close()


def make_listener(mode: str) -> EnterListener:
    """``mode`` is ``stdin``, ``evdev``, or ``auto`` (stdin if it is a terminal, else evdev)."""
    if mode == "auto":
        mode = "stdin" if sys.stdin.isatty() else "evdev"
    log.info("Enter input: %s", mode)
    return StdinEnterListener() if mode == "stdin" else EvdevEnterListener()
