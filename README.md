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

Add `--overwrite` to re-record. Override IPs with `--leader-ip` / `--follower-ip`. CSV columns are `time_s,joint_0..joint_6`
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

Every switch between motions is a smooth blend from the arm's current position and
velocity, timed so joints stay under 1 rad/s and 2 rad/s². Leading seconds spent at home
are trimmed from recordings when they are loaded (the CSVs are not modified).

If the arm is not reachable, the replayer keeps retrying. If the arm faults, it
reconnects with the error cleared and resumes idling.

Tunables: `--follower-ip`, `--window`, `--quirky-presses`, `--max-velocity`,
`--max-acceleration`, `--home-tolerance`, `--retry-delay`, `--input`.

## 3. Run at boot (headless)

```bash
deploy/install-service.sh              # installs, enables, and starts bcd-replay.service
journalctl -u bcd-replay.service -f    # watch it
sudo systemctl stop bcd-replay.service # stop (the arm parks first)
deploy/install-service.sh --uninstall
```

The service starts at boot without a login. It reads Enter directly from any keyboard
(USB button, keypad, wireless receiver) through `/dev/input`, so no terminal is needed.

Stop the service before recording or running `bcd-replay` by hand. Only one program can
drive the arm at a time.
