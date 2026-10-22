"""Shared hardware constants and arm helpers for the recorder and the replayer."""

from pathlib import Path

import numpy as np
import trossen_arm

LEADER_IP = "192.168.1.2"
FOLLOWER_IP = "192.168.1.4"

# Joint-space poses for a WXAI V0 (6 arm joints + gripper), in radians / meters.
HOME_POSE = np.array([0.0, np.pi / 2, np.pi / 2, 0.0, 0.0, 0.0, 0.0])
SLEEP_POSE = np.zeros(7)

# Trajectory names are fixed: the replayer looks for exactly these three files.
TRAJECTORY_NAMES = ("idle", "give", "quirky")
TRAJECTORY_DIR = Path("trajectories")


def trajectory_path(name: str, directory: Path = TRAJECTORY_DIR) -> Path:
    """Return the CSV path for a trajectory name, e.g. ``give`` -> ``give_motion.csv``."""
    return directory / f"{name}_motion.csv"


def connect(
    ip: str, end_effector, clear_error: bool = False, timeout: float = 20.0
) -> trossen_arm.TrossenArmDriver:
    """Create and configure a driver for a WXAI V0 arm at ``ip``.

    ``clear_error`` clears a latched controller error instead of failing on it.
    """
    driver = trossen_arm.TrossenArmDriver()
    driver.configure(trossen_arm.Model.wxai_v0, end_effector, ip, clear_error, timeout)
    return driver


def move_to(driver: trossen_arm.TrossenArmDriver, pose: np.ndarray, goal_time: float = 2.0) -> None:
    """Switch to position mode and move to ``pose``, blocking until it arrives."""
    driver.set_all_modes(trossen_arm.Mode.position)
    driver.set_all_positions(list(pose), goal_time, True)


def park(driver: trossen_arm.TrossenArmDriver) -> None:
    """Move home, then to the sleep pose. Used on every exit path."""
    move_to(driver, HOME_POSE)
    move_to(driver, SLEEP_POSE)
