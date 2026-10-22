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
