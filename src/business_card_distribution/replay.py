"""Loop the idle motion on the follower arm and react to Enter presses.

One or two presses within the window play the give motion; enough presses
(three by default) within the window play the quirky motion. Afterwards the
arm returns to idling. Presses made while a motion is playing are ignored.
"""

import argparse
import time
from collections.abc import Callable
from pathlib import Path

import numpy as np
import trossen_arm

from . import config, trajectory
from .keyboard import EnterListener
from .trajectory import Trajectory


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--follower-ip", default=config.FOLLOWER_IP)
    parser.add_argument("--dir", type=Path, default=config.TRAJECTORY_DIR, help="trajectory directory")
    parser.add_argument(
        "--window", type=float, default=1.0,
        help="seconds after the first press to count presses before deciding (default: 1.0)",
    )
    parser.add_argument(
        "--quirky-presses", type=int, default=3,
        help="presses within the window that trigger the quirky motion (default: 3)",
    )
    parser.add_argument(
        "--blend-speed", type=float, default=1.0,
        help="max joint speed in rad/s when moving between trajectories (default: 1.0)",
    )
    return parser.parse_args()


def load_all(directory: Path) -> dict[str, Trajectory]:
    missing = [n for n in config.TRAJECTORY_NAMES if not config.trajectory_path(n, directory).exists()]
    if missing:
        hint = "\n".join(f"  uv run bcd-record {n}" for n in missing)
        raise SystemExit(f"Missing trajectories in {directory}/: {', '.join(missing)}\nRecord them with:\n{hint}")
    return {n: trajectory.load(config.trajectory_path(n, directory)) for n in config.TRAJECTORY_NAMES}


class Replayer:
    def __init__(self, driver: trossen_arm.TrossenArmDriver, blend_speed: float) -> None:
        self.driver = driver
        self.blend_speed = blend_speed

    def blend_to(self, pose: np.ndarray) -> None:
        """Move to ``pose`` at no more than ``blend_speed`` on any joint, so a jump is never commanded."""
        delta = np.max(np.abs(pose - np.array(self.driver.get_positions())))
        if delta < 1e-3:
            return
        config.move_to(self.driver, pose, max(delta / self.blend_speed, 0.2))

    def play(self, traj: Trajectory, should_stop: Callable[[], bool] | None = None) -> bool:
        """Stream ``traj`` at its recorded timing. Returns True if ``should_stop`` cut it short."""
        self.blend_to(traj.positions[0])
        velocities = traj.velocities()
        t0 = time.monotonic()
        for t, q, v in zip(traj.times, traj.positions, velocities):
            if should_stop is not None and should_stop():
                return True
            delay = t0 + t - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            self.driver.set_all_positions(list(q), 0.0, False, list(v))
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


def main() -> None:
    args = parse_args()
    motions = load_all(args.dir)

    print("Connecting to follower...")
    follower = config.connect(args.follower_ip, trossen_arm.StandardEndEffector.wxai_v0_follower)
    keys = EnterListener()
    counter = PressCounter(keys, args.window, args.quirky_presses)
    replayer = Replayer(follower, args.blend_speed)

    try:
        config.move_to(follower, config.HOME_POSE)
        print(
            f"Idling. Enter = give, {args.quirky_presses}x Enter within {args.window:.1f} s = quirky. "
            "Ctrl+C to stop."
        )
        while True:
            if not replayer.play(motions["idle"], counter.gesture_complete):
                continue  # idle finished uninterrupted; loop it
            gesture = counter.take_gesture()
            print(f"-> {gesture} motion")
            replayer.play(motions[gesture])
            ignored = keys.drain()
            if ignored:
                print(f"   (ignored {ignored} press(es) during {gesture})")
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        print("Returning to sleep...")
        config.park(follower)
