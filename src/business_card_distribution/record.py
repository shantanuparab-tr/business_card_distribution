"""Record a trajectory by teleoperating the follower with the leader arm.

The leader runs in external-effort mode with force feedback from the follower
(same scheme as trossen_arm's teleoperation demo). Press Enter to start
capturing the positions commanded to the follower, Enter again to stop and save.
Recording the commands rather than the follower's measured positions means
replay sends the follower exactly what teleop did, instead of compounding its
tracking lag (and losing grip force, which comes from commanding past contact).
"""

import argparse
import time
from pathlib import Path

import numpy as np
import trossen_arm

from . import config, trajectory
from .keyboard import StdinEnterListener


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("name", choices=config.TRAJECTORY_NAMES, help="which motion to record")
    parser.add_argument("--rate", type=float, default=100.0, help="sample rate in Hz (default: 100)")
    parser.add_argument("--force-feedback-gain", type=float, default=0.1)
    parser.add_argument(
        "--gripper-offset",
        type=float,
        default=config.GRIPPER_OFFSET,
        help=f"meters subtracted from the leader gripper (default: {config.GRIPPER_OFFSET})",
    )
    parser.add_argument(
        "--show-gripper",
        action="store_true",
        help="print leader / commanded / follower gripper positions (mm) twice a second",
    )
    parser.add_argument("--dir", type=Path, default=config.TRAJECTORY_DIR, help="output directory")
    parser.add_argument("--leader-ip", default=config.LEADER_IP)
    parser.add_argument("--follower-ip", default=config.FOLLOWER_IP)
    parser.add_argument("--overwrite", action="store_true", help="replace an existing recording")
    return parser.parse_args()


def teleop_step(
    leader: trossen_arm.TrossenArmDriver,
    follower: trossen_arm.TrossenArmDriver,
    gain: float,
    gripper_offset: float,
) -> list[float]:
    """Run one teleop cycle and return the positions commanded to the follower."""
    leader.set_all_external_efforts(
        list(-gain * np.array(follower.get_all_external_efforts())), 0.0, False
    )
    target = list(leader.get_all_positions())
    target[config.GRIPPER_INDEX] -= gripper_offset
    follower.set_all_positions(target, 0.0, False, leader.get_all_velocities())
    return target


def main() -> None:
    args = parse_args()
    out_path = config.trajectory_path(args.name, args.dir)
    if out_path.exists() and not args.overwrite:
        raise SystemExit(f"{out_path} already exists; pass --overwrite to replace it")

    print("Connecting to arms...")
    leader = config.connect(args.leader_ip, trossen_arm.StandardEndEffector.wxai_v0_leader)
    follower = config.connect(args.follower_ip, trossen_arm.StandardEndEffector.wxai_v0_follower)
    config.extend_gripper_close(follower, args.gripper_offset)
    keys = StdinEnterListener()

    times: list[float] = []
    positions: list[list[float]] = []
    try:
        print("Moving to home...")
        config.move_to(leader, config.HOME_POSE)
        config.move_to(follower, config.HOME_POSE)

        leader.set_all_modes(trossen_arm.Mode.external_effort)
        follower.set_all_modes(trossen_arm.Mode.position)
        print(f"Teleoperation live. Press Enter to START recording '{args.name}'.")

        period = 1.0 / args.rate
        recording = False
        next_sample = 0.0
        next_show = 0.0
        while True:
            commanded = teleop_step(leader, follower, args.force_feedback_gain, args.gripper_offset)
            now = time.monotonic()

            if args.show_gripper and now >= next_show:
                print(
                    f"gripper mm  leader {leader.get_gripper_position() * 1000:6.2f}"
                    f"  commanded {commanded[config.GRIPPER_INDEX] * 1000:6.2f}"
                    f"  follower {follower.get_gripper_position() * 1000:6.2f}"
                    f"  follower effort {follower.get_gripper_effort():6.2f}"
                )
                next_show = now + 0.5

            if keys.poll() is not None:
                if recording:
                    break
                recording = True
                next_sample = now
                print("Recording... press Enter to STOP.")

            if recording and now >= next_sample:
                times.append(now)
                positions.append(commanded)
                # Skip missed slots rather than bursting to catch up after a slow iteration.
                next_sample = max(next_sample + period, now)
    except KeyboardInterrupt:
        print("\nInterrupted; nothing saved.")
        times.clear()
    finally:
        print("Hold still: arms are returning to sleep. Let go of the leader.")
        config.park(leader)
        config.park(follower)

    if len(times) < 2:
        print("Recording too short; nothing saved.")
        return
    trajectory.save(out_path, times, positions)
    print(f"Saved {len(times)} samples ({times[-1] - times[0]:.1f} s) to {out_path}")
