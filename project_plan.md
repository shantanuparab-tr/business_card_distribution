# Business Card Distribution — Project Plan

## Original requirements

1. Make this a git repository (GitHub user `shantanuparab-tr`).
2. Make this a Python project managed with uv (Astral).
3. Use the `trossen-arm` Python package (https://pypi.org/project/trossen-arm/1.7.2/).
4. Provide two executables:
    1. One that records a trajectory and stores it as a CSV file (all joint positions in radians).
    2. One that replays trajectories in response to a cue:
        1. The cue is an Enter keystroke.
        2. With no key press, the robot runs the idle motion.
        3. On a key press, the robot executes the give trajectory.
        4. If three presses arrive within a short time, it plays the quirky animation instead.
5. Name the trajectories "idle motion", "give motion", and "quirky motion".
6. Recording uses teleoperation mode; see the reference demo: https://github.com/TrossenRobotics/trossen_arm/blob/main/demos/python/teleoperation.py
7. The two arms are at 192.168.1.2 (leader) and 192.168.1.4 (follower).

Ask more questions if needed, and add the answers as bullet points in this document.

## Clarifications (answered)

- Implementation mode: speed.
- GitHub: private repository under `shantanuparab-tr`.
- Recording: teleoperation runs live; press Enter to start capturing and Enter again to stop and save. The motion name is a command-line argument (`idle` / `give` / `quirky`).
- Recorded data: the follower's measured joint positions (all 7 joints, including the gripper) at 100 Hz, saved to `trajectories/{idle,give,quirky}_motion.csv`.
- Triple-press detection: after the first press, wait out a 1 s window while idle keeps playing. One or two presses → give; three presses → quirky (fires as soon as the third press lands).
- Presses made during give or quirky are ignored. The arm returns to the idle loop afterwards.
- Replay uses the follower arm only.
- `trossen-arm` is pinned to **1.11.0**, not 1.7.2 as in item 3: the arms run controller firmware v1.11.1, and the driver's major.minor version must match the firmware or it refuses to connect (1.7 and 1.8 time out; 1.9 and 1.10 report a version mismatch). Upgrade the driver and the firmware together.
- Ctrl+C (or stopping the service) parks the arm(s): home pose, then sleep pose.
- IPs (confirmed 2026-10-22): leader 192.168.1.2, follower 192.168.1.4. Both tools accept `--leader-ip` / `--follower-ip` overrides.

## New requests

1. Switching from one trajectory to another should be smooth.
2. After a button press, the arm should move smoothly to the starting position of the next trajectory. Because that jump can be large, use the current and target positions to decide the goal time.
3. If a recorded trajectory begins with a few seconds at or near the home position, discard that part.
4. Run the program as a service that starts as soon as the computer powers on.
5. If the computer starts but the arms are not detected, wait until they are.
6. If the arms fail for any reason, restart the program and clear the error.
7. Make sure the service can detect the Enter keystroke, since it will run headless.

## New requests — how they were addressed

- **1–2. Smooth transitions:** every switch (idle → give/quirky, back to idle, and each time idle loops) is a quintic blend that starts at the arm's current position *and velocity* and arrives at the next trajectory's first sample with that trajectory's starting velocity, so there is no jerk. The blend duration is computed from the largest joint distance so that joint speed stays ≤ 1 rad/s and acceleration ≤ 2 rad/s² (tunable with `--max-velocity` / `--max-acceleration`). Recorded motions themselves play back at their recorded speed.
- **3. Leading home time:** when trajectories are loaded, leading samples where all six arm joints are within 0.05 rad of home are dropped (`--home-tolerance`). The CSV files are left untouched. With the current recordings this trims 1.3 s from give; idle and quirky do not start at home.
- **4. Start at boot:** a systemd service, `bcd-replay.service`, installed with `deploy/install-service.sh`. It starts at boot without anyone logging in and restarts automatically if the program ever exits.
- **5. Waiting for the arms:** the program retries the connection every 5 s indefinitely (`--retry-delay`), logging the wait once a minute.
- **6. Recovering from failures:** any arm error while running triggers a reconnect with the controller error cleared, after which the arm resumes idling from home. Note: errors are cleared automatically with no human check, so a real collision fault will also be cleared and the arm will resume.
- **7. Headless Enter detection:** the service reads key events directly from every keyboard under `/dev/input` (via `evdev`), including keyboards plugged in after boot. The service runs with the `input` group so it can read them. Enter and keypad Enter both count; holding a key down counts once.
