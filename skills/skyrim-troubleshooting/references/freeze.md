# Freeze and hang triage

A freeze leaves no crash dump, so the evidence has to be taken **from outside** while the game is still stuck. This file
is the order to take it in and the ways a freeze lies to you.

## First, decide which freeze it is

| Looks like | Is | Evidence |
|---|---|---|
| Game window alive, no input, CPU busy | **hang** — a thread is spinning or deadlocked | a busy thread that stays busy across snapshots |
| Game window alive, no input, CPU near idle | waiting on something (I/O, a driver, a lock held elsewhere, a loading thread) | the main thread parked in a system call, plus whatever it waits on |
| Stuck on a loading screen | asset or plugin load, not script logic | the last file or plugin named by the mod manager's log; the Papyrus log stops earlier |
| Screen frozen with a menu or console open | **not a hang** — the simulation is paused | frame counter static while the task queue is empty |
| Process gone, no dump | a crash the logger missed | [crash.md](crash.md) and the OS event log |

- **A frozen frame alone is not proof of a hang.** MEASURED through a live in-game bridge (an external tool, not shipped
  here): a static frame counter with an **empty task queue** is a pause, a console or a load; a static frame counter with
  **tasks pending and no task progress** is the main-thread queue starved, which is a hang. The frame counter and the task
  queue together are the discriminator; the frame counter alone cries wolf every time the user opens a menu.
- A live bridge runs on its own thread, so it answers a ping from a deadlocked game. **A ping is not proof of life**,
  and a probe dispatched onto the main thread times out in exactly the case it exists to detect (see
  [engine-quirks.md](../../skyrim-engine-knowledge/references/engine-quirks.md), *live-game probing*).

## Take the evidence before anything else

1. **Mirror the logs** (`python scripts\logs\mirror_logs.py`). On a freeze the Papyrus log is complete on disk already;
   mirror it anyway so a relaunch cannot take it away.
2. **Snapshot the threads two or three times**, seconds apart:
   `python scripts\re\thread_stacks.py --busy --ids`. It suspends each thread only while reading it, so it does not
   perturb the hang.
3. **Repeat the read, and compare.** Frames that repeat across snapshots are where a thread is stuck; a thread busy in
   the same function every time is a loop. Values on a stack that follow a call are candidates, not an unwound stack:
   trust the innermost few and the ones that repeat.
4. **Identify the main thread and its waiter.** A hung main thread usually waits (its instruction pointer sits in a
   system library); the culprit is the **busy** thread it is waiting for, which is often a job or render thread, or a
   shader/asset worker.
5. **Read the end of the Papyrus log** for the last script line and for a stack dump. The last line is a lead: the VM
   serves every script, so the last one to log is not automatically the one that hung.

`python scripts\logs\crash_triage.py [LOG]` is for dumps; for a freeze, the thread snapshot is the tool.


To read what the frozen game has in memory (quest stage, aliases, actor values, the load order it resolved), a live
bridge inside the game process is the tool — skill `skyrim-live-game`, which is also where its safety rules live. It
answers reads through a stall, which is exactly why its answers are not evidence the game is running (see below).

## The Papyrus side of a freeze

- **`VM is freezing...` / `VM is frozen`** appear on every normal exit and save. They are not a crash and carry no
  diagnostic value.
- The VM pauses while the game is paused (menu, console), and a console script toggle pauses all scripts; they resume on
  a save or a stack dump. A "frozen" VM while a menu is open is normal.
- A script stack dump is written after **5000 ms** of continuous overload. Raising the timeout, or leaving it high,
  means the dump arrives after the freeze has already been fatal: **lower it** (`iStackDumpTimeoutMS` in a script-tweak
  plugin's INI) so the offending stack is captured.
- **An error storm can degrade the VM into a freeze by itself.** The classic is an unguarded `Math.Acos`/`Asin` on NaN
  in a polling `OnUpdate`: it errors every tick (see `skyrim-engine-knowledge`, papyrus-runtime). A log with thousands of
  one-line errors per second is a freeze cause, not a symptom.
- **A page-policy crash-to-desktop is not a freeze, but it is in the same family**: the VM's internal script-memory
  policy faults (`SkyrimScript::HandlePolicy::Func4`, through `BSScript`, `SimpleAllocMemoryPagePolicy` in the stack).
  On a heavy modlist, do **not** shrink Papyrus memory page sizes; a big pool with tiny pages is pathological. The
  low-risk lever is a script-tweak plugin's `bIgnoreMemoryLimit` true→false, which re-imposes the ceiling so the VM
  freezes or dumps instead of growing into the fault. Full note: `skyrim-engine-knowledge`, papyrus-runtime.
- Two scripts locking each other deadlock; define a lock order and keep it. Papyrus is single-threaded per script
  instance, so a deadlock is always two scripts (or a script and a callback) waiting on each other.

## The usual causes, cheapest to check first

1. **A mod installed or updated since the last good run** — disable it, or roll back that one file, and retest. One
   change at a time.
2. **A duplicate SKSE plugin registering the same natives** — a stale sibling DLL. `Replacing native function` in the
   Papyrus log is the signature; see [skse-dlls.md](skse-dlls.md).
3. **An updated DLL with an outdated Address Library** — the game stops before SKSE finishes starting; see
   [skse-dlls.md](skse-dlls.md).
4. **A script loop** in a mod you added: thread snapshot plus the Papyrus log's last line, then decompile the suspect
   script (`scripts\esp\pexdis.py`, or the mod's own `.psc`).
5. **A cell or asset**: freezes when entering one place are load, not scripts; and a mesh that crashes on placement is
   a CRASH class (see [crash.md](crash.md)).
6. **A heavy live command**: MEASURED, a full physics `reset` console command reliably crashed a 700+ plugin instance —
   reproduced by typing it by hand. If a freeze followed a console command or a debug action, that is the cause and not
   the mod.

## Do not

- **Do not force-kill before mirroring the logs**, and do not relaunch "to see if it happens again" without taking the
  snapshot — that is how the evidence is lost.
- **Do not poke the running session to test a theory.** State-mutating commands pollute exactly the state you are
  diagnosing (a music-stack experiment produced phantom double tracks). Spawn dedicated test actors instead, and leave
  the player's own activity alone.
- **Do not use the player as a test attacker, target or hit recipient** in a headless session: with no headset the
  emulated body is not usable (on one install the headset pose lay on the floor).
- **Do not conclude from a menu** that a shader, an effect or an animation is broken: playback is frozen while paused, so
  a probe taken in a menu reports a false negative. Check unpaused.

## Reporting a freeze

Give the snapshots' timestamps, the busy thread's id, the innermost repeating frames with their mapped REL::IDs (or say
they are unresolved), the last Papyrus line, and which change preceded the freeze. Separate what repeats (proven) from
the function you *think* is the cause (a guess). "The main thread waits on thread 12345, which is busy in
`0x...` (`SomeMod.dll+0x...`) in both snapshots" is a report; "the game hung" is not.

Source: adapted from skyrim-ai-assistant-toolkit (c) 2026 WingedGuardian, MIT License.
