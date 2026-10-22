# Business Card Distribution: Features

A ready-to-run booth demo for the Trossen Robotics **WXAI V0** arm. The arm
greets visitors with a looping idle motion, hands out a business card at the
press of a button, and has a hidden trick for anyone who presses it three times.

You teach it every motion by hand, with a leader arm. No programming or motion
planning is needed. Once it's set up, the booth runs on its own from power-on.

For installation and step-by-step instructions, see the [README](README.md).

---

## At the booth

**Three behaviors, one button.**

| Visitor does                 | Arm does                                       |
|------------------------------|------------------------------------------------|
| Nothing                      | Plays a looping **idle** motion to draw attention |
| Presses Enter                | Performs the **give** motion: hands over a card |
| Presses Enter 3× within 1 s  | Performs the **quirky** motion: a playful surprise |

- **Any keyboard-style button works.** A USB keyboard, numeric keypad, foot
  pedal, big arcade button or wireless presenter all work, as long as it sends
  Enter. Plug it in at any time and it's picked up within seconds.
- **No double-triggering.** Presses made while the arm is mid-motion are
  ignored, so an impatient visitor can't queue up ten cards.
- **Single and triple presses are told apart reliably.** After the first press
  the arm keeps idling for a moment while it counts. A triple press is never
  mistaken for a single one.

## Smooth, natural motion

- **Seamless transitions.** Switching from idle to give, back to idle, or
  looping idle back to its start is always a smooth blend. The arm carries its
  current speed into the next motion instead of stopping or snapping.
- **Transition time adapts to the distance.** A long reach gets more time and a
  short hop less, so transitions never exceed safe joint speeds
  (1 rad/s and 2 rad/s² by default, adjustable).
- **Faithful playback.** Recorded motions replay at exactly the speed and timing
  you performed them.
- **No dead air.** If a recording starts with the arm still sitting at home
  while you got ready, that pause is skipped automatically. Your original file
  is left untouched.

## Teaching new motions

- **Record by demonstration.** Move the leader arm by hand and the follower
  copies you live. You feel resistance through the leader when the follower
  touches something.
- **One key to start, one to stop.** Press Enter to begin recording and Enter
  again to save.
- **Plain, portable files.** Each motion is a simple CSV of joint positions over
  time, easy to inspect, share, plot or version-control.
- **Safe by default.** Existing recordings are never overwritten unless you
  ask, and an aborted recording saves nothing.
- **Ships with motions.** A complete idle / give / quirky set is included, so
  the demo works straight after cloning.

## Runs unattended

- **Starts at power-on.** Installed as a system service, it starts at boot with
  no login, monitor or terminal needed. Setup is one command.
- **Waits for the arm.** If the computer boots before the arm is powered or
  plugged in, it waits patiently and connects as soon as the arm appears.
- **Recovers from faults.** If the arm faults during the show, the program
  clears the error, reconnects, and goes back to idling without anyone touching it.
- **Restarts itself.** If the program ever stops unexpectedly, the system
  restarts it within seconds.
- **Parks safely on shutdown.** Stopping the demo or the service sends the arm
  home and then into its resting (sleep) pose.
- **Readable logs.** Every connection, gesture and recovery is logged and can be
  viewed with one command.

## Easy to adjust

Change these from the command line or the service settings without touching
any code:

- how long to wait for a triple press, and how many presses trigger the quirky motion;
- how fast and how gently the arm moves between motions;
- how much of a recording's starting pause to skip;
- where the arms are on the network, and which folder of motions to use;
- whether Enter comes from the terminal or straight from the keyboards.

## What you need

- A Trossen **WXAI V0** follower arm. A second WXAI V0 with the leader end
  effector is needed only for recording new motions.
- Arm controller firmware **v1.11.x**.
- A Linux computer with a wired connection to the arms, plus any USB button or
  keyboard for visitors.

## Good to know

- **Fault recovery is fully automatic.** After any fault the arm resumes on its
  own, including one caused by bumping into something, so keep the area around
  the arm clear.
- **Playback matches your recording.** If a motion looks too fast at the booth,
  re-record it more slowly. Only the transitions between motions are speed-limited.
- **One program drives the arm at a time.** Stop the booth service before
  recording or testing by hand.

## License

BSD 3-Clause. See [LICENSE](LICENSE).
