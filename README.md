# business-card-distribution

Booth demo for a Trossen WXAI V0 arm: the follower idles, and hands out a
business card when someone presses Enter.

| Arm      | IP            |
|----------|---------------|
| Leader   | 192.168.1.2   |
| Follower | 192.168.1.4   |

## Setup

```bash
uv sync
```

## 1. Record the three motions (leader + follower)

Teleoperate the follower with the leader. Press **Enter** to start capturing,
**Enter** again to stop and save. The arms then return to sleep. Let go of the leader.

```bash
uv run bcd-record idle     # -> trajectories/idle_motion.csv
uv run bcd-record give     # -> trajectories/give_motion.csv
uv run bcd-record quirky   # -> trajectories/quirky_motion.csv
```

Add `--overwrite` to re-record. CSV columns are `time_s,joint_0..joint_6`
(joint positions in radians; `joint_6` is the gripper), sampled at 100 Hz (`--rate`).

Tip: start and end the idle recording at roughly the same pose so the loop is seamless.

## 2. Run the demo (follower only)

```bash
uv run bcd-replay
```

- No input: the idle motion loops.
- **Enter** once: give motion, then back to idle.
- **Enter ×3 within 1 s**: quirky motion.
- Presses made while give or quirky is playing are ignored.
- **Ctrl+C**: the arm moves home, then to sleep.

A single press waits out the 1 s window before give starts, so a triple press can still be detected.
Tunables: `--window`, `--quirky-presses`, `--blend-speed` (rad/s cap used when moving between motions).
