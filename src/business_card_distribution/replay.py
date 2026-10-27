"""Loop the idle motion on the follower arm and react to Enter presses.

One or two presses within the window play the give motion; enough presses
(three by default) within the window play the quirky motion. Afterwards the
arm returns to idling. Presses made while a motion is playing are ignored.

Built to run unattended as a service: it waits for the arm to appear on the
network, and if the arm faults it reconnects with the controller error cleared
and carries on.
"""

import argparse
import logging
import signal
import time
from collections.abc import Callable
from pathlib import Path

import numpy as np
import trossen_arm

from . import config, network, trajectory
from .keyboard import EnterListener, make_listener
from .trajectory import Trajectory

log = logging.getLogger("bcd-replay")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--follower-ip", default=config.FOLLOWER_IP)
    parser.add_argument("--dir", type=Path, default=config.TRAJECTORY_DIR, help="trajectory directory")
    parser.add_argument(
        "--input", choices=("auto", "stdin", "evdev"), default="auto",
        help="where Enter comes from: terminal (stdin), keyboards directly (evdev, for headless), "
        "or auto = stdin when run in a terminal, else evdev (default: auto)",
    )
    parser.add_argument(
        "--window", type=float, default=1.0,
        help="seconds after the first press to count presses before deciding (default: 1.0)",
    )
    parser.add_argument(
        "--quirky-presses", type=int, default=3,
        help="presses within the window that trigger the quirky motion (default: 3)",
    )
    parser.add_argument(
        "--max-velocity", type=float, default=1.0,
        help="joint speed limit in rad/s for transitions between motions (default: 1.0)",
    )
    parser.add_argument(
        "--max-acceleration", type=float, default=2.0,
        help="joint acceleration limit in rad/s^2 for transitions (default: 2.0)",
    )
    parser.add_argument(
        "--home-tolerance", type=float, default=0.05,
        help="leading samples within this many rad of home are trimmed from recordings (default: 0.05)",
    )
    parser.add_argument(
        "--retry-delay", type=float, default=5.0,
        help="seconds between attempts to reach the arm (default: 5)",
    )
    return parser.parse_args()


def load_all(directory: Path, home_tolerance: float) -> dict[str, Trajectory]:
    missing = [n for n in config.TRAJECTORY_NAMES if not config.trajectory_path(n, directory).exists()]
    if missing:
        hint = "\n".join(f"  uv run bcd-record {n}" for n in missing)
        raise SystemExit(f"Missing trajectories in {directory}/: {', '.join(missing)}\nRecord them with:\n{hint}")
    motions = {}
    for name in config.TRAJECTORY_NAMES:
        raw = trajectory.load(config.trajectory_path(name, directory))
        motions[name] = trajectory.trim_leading_rest(raw, config.HOME_POSE, home_tolerance)
        log.info("%s motion: %.1f s (trimmed %.1f s at home)", name, motions[name].duration,
                 raw.duration - motions[name].duration)
    return motions


class Replayer:
    """Streams trajectories to the arm, blending smoothly into each one.

    Tracks the last commanded position and velocity so a new motion can start
    from wherever the arm is, at whatever speed it is moving.
    """

    def __init__(self, driver: trossen_arm.TrossenArmDriver, max_velocity: float, max_acceleration: float) -> None:
        self.driver = driver
        self.max_velocity = max_velocity
        self.max_acceleration = max_acceleration
        driver.set_all_modes(trossen_arm.Mode.position)
        self.position = np.array(driver.get_all_positions())
        self.velocity = np.zeros_like(self.position)

    def go_to(self, pose: np.ndarray, velocity: np.ndarray | None = None) -> None:
        """Blend from the current state to ``pose``, arriving with ``velocity`` (default: at rest)."""
        if velocity is None:
            velocity = np.zeros_like(pose)
        self._stream(trajectory.blend(
            self.position, self.velocity, pose, velocity, self.max_velocity, self.max_acceleration
        ))

    def play(self, traj: Trajectory, should_stop: Callable[[], bool] | None = None) -> bool:
        """Blend into ``traj`` and stream it. Returns True if ``should_stop`` cut it short."""
        velocities = traj.velocities()
        # A looping motion whose last sample is its first runs straight back in;
        # blending there would stall the arm for the blend's minimum duration.
        already_there = (np.max(np.abs(self.position - traj.positions[0])) < 1e-3
                         and np.max(np.abs(self.velocity - velocities[0])) < 0.1)
        if not already_there:
            self.go_to(traj.positions[0], velocities[0])
        return self._stream(traj, should_stop, velocities)

    def _stream(
        self, traj: Trajectory, should_stop: Callable[[], bool] | None = None, velocities: np.ndarray | None = None
    ) -> bool:
        if velocities is None:
            velocities = traj.velocities()
        t0 = time.monotonic()
        for t, q, v in zip(traj.times, traj.positions, velocities):
            if should_stop is not None and should_stop():
                return True
            delay = t0 + t - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            self.driver.set_all_positions(list(q), 0.0, False, list(v))
            self.position, self.velocity = q, v
        return False


class PressCounter:
    """Collects presses and decides when a gesture is complete.

    A gesture is complete once ``window`` seconds have passed since its first
    press, or as soon as ``quirky_presses`` presses have arrived.
    """

    def __init__(self, keys: EnterListener, window: float, quirky_presses: int) -> None:
        self.keys = keys
        self.window = window
        self.quirky_presses = quirky_presses
        self.presses: list[float] = []

    def gesture_complete(self) -> bool:
        while (t := self.keys.poll()) is not None:
            self.presses.append(t)
        if not self.presses:
            return False
        return (
            len(self.presses) >= self.quirky_presses
            or time.monotonic() - self.presses[0] >= self.window
        )

    def take_gesture(self) -> str:
        name = "quirky" if len(self.presses) >= self.quirky_presses else "give"
        self.presses.clear()
        return name

    def reset(self) -> None:
        self.presses.clear()
        self.keys.drain()


def wait_for_arm(ip: str, retry_delay: float) -> trossen_arm.TrossenArmDriver:
    """Connect to the follower, retrying forever. Any latched controller error is cleared."""
    attempts = 0
    while True:
        attempts += 1
        try:
            driver = config.connect(
                ip, trossen_arm.StandardEndEffector.wxai_v0_follower, clear_error=True, timeout=retry_delay
            )
            config.extend_gripper_close(driver)
            log.info("connected to follower at %s", ip)
            check_controller_network(driver, ip)
            return driver
        except Exception as e:
            # Log the first failure and then once a minute, so a long wait doesn't flood the journal.
            if attempts == 1 or attempts % max(1, int(60 / retry_delay)) == 0:
                log.warning("follower at %s not reachable yet (%s); retrying every %.0f s", ip, e, retry_delay)
                log.warning("network: %s", network.diagnose(ip, config.FOLLOWER_CONNECTION))
            time.sleep(retry_delay)


def check_controller_network(driver: trossen_arm.TrossenArmDriver, ip: str) -> None:
    """Warn if the controller's stored IP settings won't survive its next reboot on this port."""
    host_address = network.port_address(config.FOLLOWER_CONNECTION)
    if host_address is None:
        return
    try:
        problems = network.controller_problems(driver, ip, host_address)
    except Exception as e:
        log.warning("could not read the controller's network settings: %s", e)
        return
    for problem in problems:
        log.warning("controller network setting: %s; fix it with the set_manual_ip demo", problem)


def run(replayer: Replayer, motions: dict[str, Trajectory], counter: PressCounter) -> None:
    """Idle, react to presses, repeat. Only returns by raising."""
    replayer.go_to(config.HOME_POSE)
    counter.reset()
    log.info("idling. Enter = give, %dx Enter within %.1f s = quirky", counter.quirky_presses, counter.window)
    while True:
        if not replayer.play(motions["idle"], counter.gesture_complete):
            continue  # idle finished uninterrupted; loop it
        gesture = counter.take_gesture()
        log.info("-> %s motion", gesture)
        replayer.play(motions[gesture])
        ignored = counter.keys.drain()
        if ignored:
            log.info("ignored %d press(es) during %s", ignored, gesture)


def _raise_keyboard_interrupt(signum, frame):
    raise KeyboardInterrupt


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # systemd stops the service with SIGTERM; treat it like Ctrl+C so the arm parks.
    signal.signal(signal.SIGTERM, _raise_keyboard_interrupt)

    motions = load_all(args.dir, args.home_tolerance)
    keys = make_listener(args.input)
    counter = PressCounter(keys, args.window, args.quirky_presses)

    while True:
        driver = None
        replayer = None
        try:
            driver = wait_for_arm(args.follower_ip, args.retry_delay)
            replayer = Replayer(driver, args.max_velocity, args.max_acceleration)
            run(replayer, motions, counter)
        except KeyboardInterrupt:
            log.info("stopping; returning to sleep")
            if replayer is not None:
                try:
                    replayer.go_to(config.HOME_POSE)
                    replayer.go_to(config.SLEEP_POSE)
                except Exception:
                    log.exception("could not park the arm")
            return
        except Exception:
            log.exception("arm failure; reconnecting with the error cleared in %.0f s", args.retry_delay)
            if driver is not None:
                try:
                    log.warning("controller error: %s", driver.get_error_information())
                except Exception:
                    pass
                try:
                    driver.cleanup()
                except Exception:
                    pass
            time.sleep(args.retry_delay)
