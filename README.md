# business-card-distribution

Booth demo for a Trossen Robotics WXAI V0 arm. The follower arm plays a looping
idle motion. When a visitor presses Enter, it hands out a business card (the
*give* motion). Press Enter three times quickly and it does something silly
instead (the *quirky* motion).

The repository ships with recorded trajectories, so you can run the demo
straight away, or record your own with a leader arm.

For a feature overview, see [FEATURES.md](FEATURES.md).

- [How it works](#how-it-works)
- [Hardware and network](#hardware-and-network)
- [Install](#install)
- [Usage 1: Replay in a terminal](#usage-1-replay-in-a-terminal)
- [Usage 2: Run as a boot service (headless booth)](#usage-2-run-as-a-boot-service-headless-booth)
- [Usage 3: Record new trajectories](#usage-3-record-new-trajectories)
- [Command reference](#command-reference)
- [Trajectory file format](#trajectory-file-format)
- [Troubleshooting](#troubleshooting)

## How it works

| Input                         | What the arm does                           |
|-------------------------------|---------------------------------------------|
| Nothing                       | Loops the **idle** motion                   |
| Enter once (or twice)         | Plays the **give** motion, then idles again |
| Enter 3× within 1 second      | Plays the **quirky** motion, then idles     |
| Enter while give/quirky plays | Ignored                                     |

- After the first press, the program waits 1 s to count presses (idle keeps
  playing meanwhile), so a triple press is never mistaken for a single one.
- Every switch between motions is a smooth blend from the arm's current position
  *and speed* into the next motion. Its duration is computed from the distance,
  keeping joints under 1 rad/s and 2 rad/s². Nothing ever jumps.
- Any seconds at the start of a recording where the arm is still sitting at home
  are skipped on load. The CSV files are not modified.
- If the arm isn't reachable, the program keeps retrying. If the arm faults
  mid-run, it reconnects with the controller error cleared and resumes idling.
- On Ctrl+C or a service stop, the arm moves home, then to its sleep pose.

## Hardware and network

| Device              | Role                                    | IP          |
|---------------------|-----------------------------------------|-------------|
| WXAI V0, leader EE  | Recording only (you move it by hand)    | 192.168.1.2 |
| WXAI V0, follower EE| Recording and replay                    | 192.168.1.4 |
| Computer            | Runs this project                       | any free 192.168.1.x, e.g. 192.168.1.15 |

Replay needs only the follower. Recording needs both arms.

The arm controllers have static IPs, so the computer's wired port needs a static
address on the same subnet. With NetworkManager (replace `enp0s31f6` with your
interface from `ip -br link`):

```bash
nmcli con add type ethernet ifname enp0s31f6 con-name trossen-arms \
    ipv4.method manual ipv4.addresses 192.168.1.15/24
nmcli con up trossen-arms
ping -c1 192.168.1.4    # the follower should answer
```

**Firmware version matters.** This project uses `trossen-arm` **1.11.0**, which
only connects to arms running controller firmware **v1.11.x**. A different
firmware gives either endless "Retransmission attempt" warnings or "The major
and minor versions of the driver and controller firmware must match". If you
update the firmware, update the `trossen-arm` pin in `pyproject.toml` to match.

## Install

Requires Linux and [uv](https://docs.astral.sh/uv/getting-started/installation/).
uv fetches the right Python (3.12+) by itself.

```bash
git clone https://github.com/shantanuparab-tr/business_card_distribution.git
cd business_card_distribution
uv sync
```

This creates `.venv/` with two commands: `bcd-record` and `bcd-replay`.
Run them with `uv run <command>` from the project directory.

## Usage 1: Replay in a terminal

Good for testing and tuning. Make sure the boot service is **not** running
(`sudo systemctl stop bcd-replay.service`). Only one program can drive the arm at a time.

```bash
uv run bcd-replay
```

Press Enter in that terminal to trigger give, or Enter three times quickly for
quirky. Ctrl+C parks the arm and exits.

Common variations:

```bash
uv run bcd-replay --window 1.5              # allow a slower triple press
uv run bcd-replay --max-velocity 0.6        # gentler transitions between motions
uv run bcd-replay --dir my_trajectories     # use a different set of recordings
uv run bcd-replay --follower-ip 192.168.1.7 # follower at another address
uv run bcd-replay --input evdev             # read Enter from any keyboard, not this terminal
```

## Usage 2: Run as a boot service (headless booth)

This is how the booth runs for real. The program starts at power-on with no
login and no monitor. Enter presses are read straight from any USB keyboard,
keypad, button or wireless receiver.

### Set up the service

1. Do the [Install](#install) and [network](#hardware-and-network) steps, and
   check the arm answers: `ping 192.168.1.4`.
2. Check the trajectories are in `trajectories/` (they ship with the repo).
3. Install and start the service (run as your normal user; it asks for sudo):

   ```bash
   deploy/install-service.sh
   ```

   This runs `uv sync`, writes `/etc/systemd/system/bcd-replay.service` set to run
   as you from this directory, then enables and starts it. Don't move or delete
   the project directory afterwards: the service runs from it.

4. Watch it come up:

   ```bash
   journalctl -u bcd-replay.service -f
   ```

   You should see `connected to follower` and then `idling`. Press Enter on the
   keyboard or button and look for `-> give motion`.

5. Reboot once to confirm it starts by itself: `sudo reboot`.

### Operate the service

```bash
systemctl status bcd-replay.service          # running?
journalctl -u bcd-replay.service -f          # live log
journalctl -u bcd-replay.service -b          # everything since this boot
sudo systemctl stop bcd-replay.service       # stop (arm parks first)
sudo systemctl start bcd-replay.service      # start again
sudo systemctl restart bcd-replay.service    # pick up new trajectories
sudo systemctl disable bcd-replay.service    # stop starting at boot
deploy/install-service.sh --uninstall        # remove completely
```

To change options (for example `--window 1.5`), edit the `ExecStart=` line in
`deploy/bcd-replay.service.in` and re-run `deploy/install-service.sh`.

### What the service does on its own

- **Arm off or unplugged at boot:** it waits, retrying every 5 s, and logs once a minute.
- **Arm faults while running:** it reconnects, clears the error, goes home, and resumes idling.
  This is automatic with no human check, so the arm also resumes after a real
  collision. Keep the area around it clear.
- **The program crashes:** systemd restarts it after 5 s, indefinitely.
- **Keyboard plugged in late or swapped:** picked up within a few seconds.

The service reads keyboards through `/dev/input`. It is granted the `input`
group for that, so your user account doesn't need it. Every key press on the
machine is visible to the service, but only Enter does anything.

## Usage 3: Record new trajectories

Recording needs both arms. Stop the service first:
`sudo systemctl stop bcd-replay.service`.

```bash
uv run bcd-record idle   --overwrite   # -> trajectories/idle_motion.csv
uv run bcd-record give   --overwrite   # -> trajectories/give_motion.csv
uv run bcd-record quirky --overwrite   # -> trajectories/quirky_motion.csv
```

For each one:

1. **Clear the space around both arms.** They move to the home pose by themselves at start.
2. Teleoperation goes live: moving the leader by hand moves the follower, and you
   feel resistance through the leader when the follower pushes against something.
3. Press **Enter** to start recording and perform the motion.
4. Press **Enter** again to stop. The file is saved and both arms return to sleep.
   Let go of the leader when they start moving.

Without `--overwrite`, `bcd-record` refuses to replace an existing recording.
Ctrl+C aborts without saving. Use `--dir` to record into another folder.

Tips:

- **idle** loops forever, so end it close to where it started. The blend covers
  small gaps, but the closer the better.
- Lingering at home before you start moving is fine; it's trimmed on replay.
- Replay reproduces your recorded speed exactly, so move as smoothly as you want
  the booth to look.

Then test with `uv run bcd-replay`, commit the new CSVs, and restart the service.

## Command reference

### `bcd-record NAME`

| Option | Default | Meaning |
|---|---|---|
| `NAME` | (required) | `idle`, `give`, or `quirky` |
| `--rate` | 100 | Samples per second |
| `--force-feedback-gain` | 0.1 | How strongly the leader resists when the follower meets force |
| `--dir` | `trajectories` | Output folder |
| `--leader-ip` | 192.168.1.2 | Leader arm address |
| `--follower-ip` | 192.168.1.4 | Follower arm address |
| `--overwrite` | off | Replace an existing recording |

### `bcd-replay`

| Option | Default | Meaning |
|---|---|---|
| `--follower-ip` | 192.168.1.4 | Follower arm address |
| `--dir` | `trajectories` | Folder holding the three CSVs |
| `--input` | `auto` | `stdin` (terminal), `evdev` (any keyboard, headless), or `auto` (terminal if there is one, else evdev) |
| `--window` | 1.0 | Seconds after the first press to count presses |
| `--quirky-presses` | 3 | Presses within the window that trigger quirky |
| `--max-velocity` | 1.0 | Joint speed limit for transitions, rad/s |
| `--max-acceleration` | 2.0 | Joint acceleration limit for transitions, rad/s² |
| `--home-tolerance` | 0.05 | Leading samples within this many rad of home are skipped |
| `--retry-delay` | 5.0 | Seconds between attempts to reach the arm |

## Trajectory file format

`trajectories/<name>_motion.csv`: a header, then one row per sample:

```
time_s,joint_0,joint_1,joint_2,joint_3,joint_4,joint_5,joint_6
0.000000,0.001234,1.570000,...
```

`time_s` counts seconds from the start of the recording. `joint_0`–`joint_5` are
arm joint positions in radians, and `joint_6` is the gripper opening in meters. These are
the follower's measured positions, sampled at 100 Hz.

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `Retransmission attempt N failed`, then `Not configured` | Arm unreachable, or firmware ≠ v1.11. Check `ping`, then the firmware note above. |
| `driver and controller firmware must match` | Firmware version mismatch; see [Hardware and network](#hardware-and-network). |
| Service log: `no keyboard found yet` | No keyboard plugged in, or the service isn't running with the `input` group. Re-run `deploy/install-service.sh`. |
| Enter does nothing under the service | Check `journalctl` for `listening for Enter on ...` lines naming your device. |
| `Missing trajectories` | Record the missing motion, or point `--dir` at the right folder. |
| `bcd-record` or `bcd-replay` can't connect while the service runs | Only one program can drive the arm. `sudo systemctl stop bcd-replay.service`. |
| Arm jerks between motions | Lower `--max-velocity` / `--max-acceleration`. |

## License

BSD 3-Clause. See [LICENSE](LICENSE).
