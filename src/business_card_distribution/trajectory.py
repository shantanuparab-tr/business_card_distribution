"""CSV storage for recorded joint trajectories.

File format: a header row ``time_s,joint_0,...,joint_6`` followed by one row per
sample. ``time_s`` is seconds since the start of the recording; joints are in
radians (the gripper, joint_6, is in meters as reported by the driver).
"""

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class Trajectory:
    times: np.ndarray  # shape (N,), seconds from the first sample, monotonically increasing
    positions: np.ndarray  # shape (N, num_joints)

    def __post_init__(self) -> None:
        if len(self.times) < 2:
            raise ValueError("a trajectory needs at least two samples")
        if self.positions.shape[0] != len(self.times):
            raise ValueError("times and positions have different lengths")

    @property
    def duration(self) -> float:
        return float(self.times[-1])

    def velocities(self) -> np.ndarray:
        """Finite-difference joint velocities, used as feedforward during replay."""
        return np.gradient(self.positions, self.times, axis=0)


def save(path: Path, times: list[float], positions: list[list[float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    num_joints = len(positions[0])
    t0 = times[0]
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["time_s"] + [f"joint_{i}" for i in range(num_joints)])
        for t, q in zip(times, positions):
            writer.writerow([f"{t - t0:.6f}"] + [f"{x:.6f}" for x in q])


def load(path: Path) -> Trajectory:
    data = np.loadtxt(path, delimiter=",", skiprows=1, ndmin=2)
    return Trajectory(times=data[:, 0], positions=data[:, 1:])


def trim_leading_rest(traj: Trajectory, pose: np.ndarray, tolerance: float) -> Trajectory:
    """Drop the leading samples where the arm is still within ``tolerance`` rad of ``pose``.

    Recordings start at the home pose, so they usually open with a second or two
    of nothing happening. Only the six arm joints are compared; the gripper's
    range (meters) is too small for a radian tolerance. One at-rest sample is kept
    so playback starts from rest. A trajectory that never leaves ``pose`` is
    returned unchanged.
    """
    distance = np.max(np.abs(traj.positions[:, :6] - pose[:6]), axis=1)
    moving = np.flatnonzero(distance > tolerance)
    if len(moving) == 0 or moving[0] <= 1:
        return traj
    start = moving[0] - 1
    return Trajectory(times=traj.times[start:] - traj.times[start], positions=traj.positions[start:])


def blend(
    q0: np.ndarray,
    v0: np.ndarray,
    q1: np.ndarray,
    v1: np.ndarray,
    max_velocity: float,
    max_acceleration: float,
    rate: float = 100.0,
    min_duration: float = 0.3,
) -> Trajectory:
    """Quintic transition from (q0, v0) to (q1, v1), starting and ending with zero acceleration.

    Matching velocity at both ends means switching motions mid-move has no jerk.
    The duration scales with the largest arm-joint distance: a rest-to-rest quintic
    over distance d and time T peaks at 1.875*d/T velocity and 5.77*d/T^2
    acceleration, so T is the smallest time that keeps both under their limits.
    """
    distance = float(np.max(np.abs(q1[:6] - q0[:6])))
    duration = max(
        min_duration,
        1.875 * distance / max_velocity,
        np.sqrt(5.774 * distance / max_acceleration),
    )
    T = duration
    dq = q1 - q0
    a3 = (20 * dq - (8 * v1 + 12 * v0) * T) / (2 * T**3)
    a4 = (-30 * dq + (14 * v1 + 16 * v0) * T) / (2 * T**4)
    a5 = (12 * dq - 6 * (v1 + v0) * T) / (2 * T**5)
    times = np.append(np.arange(0.0, T, 1.0 / rate), T)
    t = times[:, None]
    positions = q0 + v0 * t + a3 * t**3 + a4 * t**4 + a5 * t**5
    return Trajectory(times=times, positions=positions)
