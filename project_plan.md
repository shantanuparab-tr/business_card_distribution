1. Make this into a git repo. (user shatanuparab-tr)
2. Make this into a python project use UV (astral)
3. We need to use trossen_arm python package (https://pypi.org/project/trossen-arm/1.7.2/)
4. We need 2 executables 
    a. records and stores a trajectory as csv files. (all joint positions in radians).
    b. this one has a few task, it will replay the trajectory given a cue.
        i. The cue is a Enter keystroke.
        ii. The robot will be running idle motion (no keypress)
        iii. On key press the robot will exectue the give trjectory
        iv. if 3 consecutive presses are done withing a brief time period it will play the quirky animation
5. name the trajectories as follows. "idel motion", "give motion" and "quirky motion".
6. USe the follwoing for understanding the recording process. We will be using teleoperation mode. (https://github.com/TrossenRobotics/trossen_arm/blob/main/demos/python/teleoperation.py)
7. The 2 arms will have Ip 192.168.1.2(leader) and 192.168.1.4(follower)

Ask more questions if needed and add the answers as bullet point in this document
## Clarifications (answered)
- Implementation mode: speed.
- GitHub: private repo under `shantanuparab-tr` (the logged-in gh account; the plan's "shatanuparab-tr" was a typo).
- Recording: teleop runs live; press Enter to start capturing, Enter again to stop and save. Motion name is a CLI arg (`idle` / `give` / `quirky`).
- Recorded data: follower's measured joint positions (all 7 incl. gripper) at 100 Hz → `trajectories/{idle,give,quirky}_motion.csv`.
- Triple-press disambiguation: after the first press, wait out a 1 s window while idle keeps playing. 1–2 presses → give, 3 presses → quirky (fires as soon as the 3rd lands).
- Presses during give/quirky are ignored. The arm returns to the idle loop afterwards.
- Replay uses the follower only (192.168.1.4). Transitions between motions are rate-limited (1 rad/s) so the arm never jumps.
- trossen-arm pinned to 1.7.2, whose API uses `get_positions`/`get_velocities`/`get_external_efforts` (the linked demo on `main` uses `get_all_*`).
- Ctrl+C on either tool parks the arm(s): home pose, then sleep pose.
