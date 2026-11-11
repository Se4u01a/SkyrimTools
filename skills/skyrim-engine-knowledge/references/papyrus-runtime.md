# Papyrus runtime: lifecycle, threading, timing, tricks

What the VM does, as opposed to what a function's signature says. Signatures are `papyrus-reference`; this file is
behaviour. Compiling is `papyrus-compiler`.

Evidence labels: **MEASURED** (observed on one install, with the date the source gives), **READ** (from a wiki, a
decompiled script or a changelog), **INFERRED** (a conclusion nobody checked), **UNSOURCED** (community claim, not
checked here).

## Script lifecycle

- `OnInit` fires once, when the script first initialises, and **not again after a save/load** — a quest must be reset
  for it to fire again.
- For Quest and Alias scripts `OnInit` fires at game startup and whenever the quest starts (a reset counts); for Topic
  Infos, perks and persistent refs, at first load into the session.
- Every property and variable is reset to its default value *before* `OnInit` fires.
- A quest script has **no `OnLoad`**. `OnLoad` on an ObjectReference means its 3D loaded, not that a save was loaded —
  use `RegisterForSingleUpdate`/`OnUpdate`, or `OnGameReload`, to detect a reload.
- Auto properties receive their default values after save/load. **Non-auto properties do NOT receive the master file's
  values after save/load** — they stay blank.
- A variable that references a Form from a removed mod becomes "missing" and **stays missing** if the mod is restored.
- FormList entries added by a script persist through save/load.
- ObjectReferences are temporary by default: only the base Form is stored in a save. `PlaceAtMe` with persistence, or a
  ReferenceAlias, makes a reference persist.
- **Orphaned script instances** come from objects removed before their script threads finished, and from uninstalled
  mods. They do not cause serious save bloat but they do mean cleanup was incomplete, and a removed mod's
  `RegisterForUpdate` handlers keep firing and log errors periodically.

READ: CK wiki *OnInit*, *Save Files Notes (Papyrus)*.

## Threading model

- Papyrus is **single-threaded per script instance**; concurrent calls queue FIFO.
- The default `fUpdateBudgetMS` is **1.2 ms per frame for all scripts combined**, and the VM runs about **100
  operations per task**. When the budget is exhausted, execution resumes next frame.
- `iMaxAllocatedMemoryBytes` is the total stack-frame memory ceiling; when it is reached the VM waits instead of
  allocating.
- A script stack dump is written after **5000 ms** of continuous overload. Incoming events are then dropped; `Wait()`
  continuations are not.
- Payload-style native payload mods bypass Papyrus entirely and can fire while scripts are running.
- **Out-of-order event delivery is real**: `OnTriggerLeave` can arrive before `OnTriggerEnter`. Use counters, not
  booleans.
- Two scripts calling the same function queue against each other; a popular function gets progressively slower.
- The VM freezes while the game is paused (menu, console). Toggling scripts from the console pauses all of them; they
  resume on a save or a stack dump.
- With 700+ plugins the 1.2 ms budget is frequently exceeded, which is what makes `Wait()` and event dispatch drift
  (below).

READ: CK wiki *Threading Notes (Papyrus)*, an analysis of the Papyrus INI settings.

## Utility.Wait() is frame-bounded, never skipped, never exact

- `Wait()` resolution is one frame — ~11 ms at 90 fps — and it is **never skipped**: the engine defers, then always
  resumes.
- Sub-100 ms waits (`Wait(0.05)`) are unreliable under script load and can fire 2-3× late.
- Under extreme load (700+ plugins) jitter reaches 200-500 ms occasionally; `Wait(0.1)` was measured rounding to
  ~0.5-1 s.
- **Prefer `RegisterForSingleUpdate`/`OnUpdate`** over `Wait()`: it avoids stack problems with long waits.
- For FX sequencing, merge sub-100 ms gaps into the adjacent step.
- 18-20 ms precision is not achievable in Papyrus at all — that needs native C++ (an SKSE plugin).

## RegisterForUpdate vs RegisterForSingleUpdate

- `RegisterForUpdate` is a repeating loop that survives its mod being removed, and then logs errors forever.
- `RegisterForSingleUpdate` fires once and must be re-registered; **chaining it is the safer pattern**.
- Anything you intend to *tune* belongs in a GlobalVariable the script reads each run, not in a constant — see
  "Iterate without recompiling" in the troubleshooting skill's Papyrus reference.

## States

- `OnBeginState` does **not** fire if the script is already in that state.
- `GoToState("")` inside `OnUnload` triggers `OnEndState` with `Self` None/null and crashes. Move the
  `GoToState("")` call into `OnLoad`.

## Magic effects: start, finish, casting types

- `OnEffectStart` fires when the effect activates on its target; `OnEffectFinish` when it ends.
- **When `OnEffectFinish` fires the effect may already be deleted** — calling methods on it can fail. Guard the
  handler, especially for a dead actor (see the corpse-despawn trap below).
- **All effects on a spell or enchantment must share one casting type.** Mismatched casting types cause unpredictable
  behaviour or a spell that never fires. (Constant Effect = ability-like, Fire-and-Forget = charge then fire,
  Concentration = held.)
- Delivery types: Self applies to the caster, Touch on contact, Aimed on the hit target.
- Spell vs Ability vs Power behave differently for cooldown, stacking and activation: a power equips to the shout key
  (Greater Power = once a day; Lesser Power = unlimited or a custom cooldown), an ability is passive with no duration.
- **A Concentration + Script-archetype MGEF fires `OnEffectStart` at engine framerate** — dozens of times a second,
  each a separate script instance. Anything cast or registered inside it spams unless a script-level boolean gates it
  (set on first fire, reset in `OnEffectFinish`). `HasMagicEffect()` races with the cast: the effect has not registered
  by the time the next `OnEffectStart` fires.
- A Concentration + ValueModifier MGEF drains continuously at engine speed and its magnitude is **per second**.
- **A recompiled `.pex` only loads at game startup** — see the troubleshooting skill's Papyrus reference for the
  refresh procedure and the design rule it forces.

## RemoveSpell vs DispelSpell (and abilities)

- `RemoveSpell()` drops the spell from the actor's list and does **not** fire `OnEffectFinish`.
- `DispelSpell()` cancels the active effect and **does** fire `OnEffectFinish` — but it **excludes ability-type
  spells** and silently does nothing on them.
- So: a magic-effect script with cleanup in `OnEffectFinish` (restore weather, re-enable AI, delete placed objects)
  needs `DispelSpell()`, and an ability needs `RemoveSpell()`.
- `AddSpell()` on an ability the actor already has is a safe no-op: no stacking, no error.
- **`Self.Dispel()` on an ActiveMagicEffect dispels only that effect**, not the spell. For a spell with 8 effects,
  dispelling one leaves 7 running with their summoned objects visible; use `actor.DispelSpell(spellForm)` to end the
  whole spell.
- GlobalVariable signals between scripts work, but a global is **sticky**: a signal set with no handler running
  persists. Clear signal globals in `OnEffectStart`.

## Corpse despawn when a freeze effect ends

- Symptom: an enemy frozen by a scripted effect (AI disabled + paralysed) is killed *while frozen* and **vanishes**
  instead of leaving a corpse, at the moment the effect ends.
- Cause: the freeze MGEF's `OnEffectFinish` re-enables AI or clears paralysis **without checking `IsDead()`**;
  re-animating a corpse despawns it. `OnEffectStart` is usually guarded, `OnEffectFinish` often is not.
- Fix (confirmed working): return early from `OnEffectFinish` when the target is dead. The despawn happens at
  *finish*, so commenting out a ragdoll-removal call in `OnEffectStart` is the wrong fix.

```papyrus
Event OnEffectFinish(Actor akTarget, Actor akCaster)
    if akTarget.IsDead()
        return
    endif
    ; ... existing un-freeze cleanup ...
EndEvent
```

## Actor values and equipment

- `SetActorValue` sets the **base** (maximum) value, not the current one. `RestoreActorValue` adds to current up to
  the base. `ModifyActorValue` changes **both** current and base. `DamageActorValue`/`RestoreActorValue` change
  current only.
- `EquipItem` gives the item first if the actor lacks it — `AddItem` first when you want that to be explicit.
- Enchanted weapon charges reset to full when the actor is not in a loaded cell.
- `abPreventEquip` does not work on NPCs (ammo only).
- `QueueNiNodeUpdate()` (SKSE) is needed after `EquipItem` to force the visual update.
- `NetImmerse.SetNodeScale(actor, "WEAPON", scale, false)` scales the WEAPON bone and its children (including the
  equipped weapon mesh) with **one call**, and the engine renders it at framerate. Call `QueueNiNodeUpdate()` after it
  to flush the change. It needs a visible weapon equipped; scaling an invisible one leaves it invisible. Confirmed
  working in VR (**MEASURED** by the source's author).
- `SetVehicle(None)` does not reliably dismount; players stay stuck. Setting a custom creature as a vehicle crashes
  without matching `.hkx` animations. There is no `IsRidingHorse`; the workaround reads the `bIsRiding` animation
  variable. In VR it desyncs the HMD (see [vr-differences.md](vr-differences.md)).

## Spawning and moving objects from script

- `PlaceAtMe(form, 1, false, true)` — the 4th parameter creates the object **disabled**, which is the fix for a
  large `SetScale()` object visibly flickering at the caster's feet. Position it while invisible, then `EnableNoWait()`.
- `PlaceAtMe()` then immediately `SetMotionType()` fails in VR: the 3D is not loaded yet and the call errors with
  "has no 3d, and so cannot have its motion type changed". Wait on `Is3DLoaded()` first (**MEASURED** in VR; the same
  guard is the one that stops the spawned-actor Havok CTD, below).
- **Papyrus-positioned objects update at ~1 Hz visually** with 700+ plugins. `SetPosition()` per tick teleports
  visibly; `StopTranslation()` + `TranslateTo()` per tick gets no smoother. `TranslateTo()` at a moderate speed
  (e.g. 8000 u/s) lets the engine interpolate, but the object still trails ~0.5 s behind.
- For smooth visual tracking use an engine-level route (a node scale, an animation, a projectile) rather than per-tick
  positioning.
- `While i < 180` with `sin(i)`/`cos(i)` produces a **semicircle** (0°-180° is right → bottom → left). A full ring is
  `< 360`. A formation radius above ~1300 game units puts objects past typical render distance; 1800 units (~25 m) was
  too far for swords to be visible.
- Spawning 270 objects from one `OnEffectStart` worked without a crash but took seconds, and `OnUpdate` does not start
  until `OnEffectStart` returns.

## Spawned-actor Havok CTD (null physics body)

`PushActorAway` or a lethal `DamageActorValue` on a freshly `PlaceAtMe`'d or otherwise just-spawned actor whose 3D and
Havok body have not loaded is an `EXCEPTION_ACCESS_VIOLATION` CTD. Guard every physics operation behind an
`Is3DLoaded()` wait-loop before touching a spawned actor.

## Actor value probing traps

- `GetActorValue("IsBlocking")` is **not an actor value**: it errors on every call (`Actor value "IsBlocking" does not
  exist`) and that error has real VM cost in a hot path. Use `Actor.GetAnimationVariableBool("IsBlocking")`, which
  reads the animation-graph variable. Creature and animal graphs may not supply it — there the call logs a
  missing-variable error and returns false, so skip races without the variable instead of probing every hit.
- The `IsBlocking` **condition function** evaluates its subject natively; if the subject can be a non-actor reference
  (a cone or area effect hitting a door), guard it with `IsActor == 1` first. INFERRED from one VR crash log; the guard
  is cheap either way.
- `GetActorBase().GetName()` returns empty for levelled actors (trolls, bandits); `GetDisplayName()` is the one to use
  in text.

## PushActorAway: caller is the source

`Actor.PushActorAway(akActorToPush, afKnockbackForce)` pushes the **passed-in actor away from `Self`**.

- `Caster.PushActorAway(target, 15.0)` → the target flies away from the player. Correct.
- `target.PushActorAway(caster, 15.0)` → the **player** flies away from the target. This is the classic
  self-knockback bug: the enemy takes damage and no knockback, the player gets launched.
- For a visible stagger, `PushActorAway(caster, 1.0-3.0)` reads as a stumble and is engine-native.

## Null references, and the guard that is not a guard

- "Cannot call X() on a None object" is an operation on a null value. Check for `None` before operations.
- `IsHostileToActor` **crashes to desktop** with a NONE object (vanilla bug).
- **`GetTargetActor() == None` is not a valid unbound-`Self` guard.** When an ActiveMagicEffect script's `Self` has no
  native binding (phantom instances from an equip or ability re-broadcast), calling *any* native function on it logs
  `Unable to call X - no native object bound` and returns a **non-None garbage value**, so the `== None` test never
  triggers and the check itself adds an error. This contradicts common Papyrus advice; trust the log. There is no
  in-script way to short-circuit a phantom instance — fix the source (reduce the re-broadcast, detach the script at
  record level, filter natively).

## GetFormFromFile and record ownership

- `Game.GetFormFromFile(formID, "plugin.esp")` resolves forms at runtime without properties, which avoids a large VMAD.
- The `formID` is the **local** FormID without the load-order prefix; it needs the `0x` prefix (`0x0001ABCD`).
- It returns `None` when the plugin is not loaded, so **check before casting**, and a FormID's prefix must match the
  plugin's master count (an ESP with 5 masters uses index `0x05`), or the lookup silently returns `None`.
- **Never borrow another mod's records this way.** A soft runtime dependency breaks silently when that mod is disabled,
  uninstalled or reordered. Copy the record (SNDR, SPEL, MGEF, …) into your own plugin instead.
- Hard master dependencies listed in MAST records are acceptable when you deliberately override or extend that mod.
- `Skyrim.esm` and the core masters are always loaded, but another plugin can still **override** their records: a bare
  FormID is fine for a marker or an anchor, and any vanilla record whose behaviour your mod relies on should be copied.

## Performance: what actually costs

Ordered by cost: native function calls (biggest), property access on another script (a function call), string
operations, complex conditional logic.

- Cache property values in local variables, minimize native calls, prefer auto properties.
- Default arrays are limited to **128 items** (PapyrusUtil/JContainers for more).
- Arrays are **pass-by-reference**: modifying an element affects every reference to that array.
- Gate a polling loop's expensive work behind a cheap change test and return early. In a 10 Hz loop doing per-swing
  work (knockback tier, bleed cast, form lookup), most ticks are "direction unchanged", so
  `if !dirChanged : return` collapses the per-tick cost to one dot product.
- Remove `Debug.Notification()` from tight loops; the notification queue is slow and per-tick overhead.

## Conditions and NaN

- **`OR` has precedence over `AND`**: `A AND B OR C AND D` evaluates as `(A AND (B OR C) AND D)`, not
  `(A AND B) OR (C AND D)`.
- More than three AND-pairs is a performance problem on high-demand items (spells, effects).
- Some condition functions have no Papyrus equivalent (e.g. `IsPlayerInRegion`); `GetIsRace` does not always recognise
  race, where `GetRace()` does.
- `Math.Acos(x)`/`Math.Asin(x)` error ("Argument for acos out of range") for any x outside [-1, 1] **including NaN**,
  and a zero-length vector normalised into a dot product produces NaN. **The usual clamp does not catch it**:
  `NaN > 1.0` and `NaN < -1.0` are both false. **MEASURED** on one Skyrim VR install, the Papyrus VM also returned
  **true** for the inclusive test `x >= -1.0 && x <= 1.0` with x = NaN, so an inclusive membership check is not a
  finite-value check either. Validate with strict comparisons, handle the endpoints explicitly, then call
  `Acos`/`Asin`. In a polling `OnUpdate` an unguarded call errors every tick, and that error storm can degrade the VM
  until the game freezes.

## Real-time actor detection: GetNthRef is not reliable

- `Cell.GetNumRefs(0)` + `Cell.GetNthRef(i, 0)` does **not** reliably return all loaded actors. **MEASURED** in VR: a
  Frost Troll continuously hit by an engine beam appeared in only 2 of 24 consecutive scans (~1 s each), while the ref
  count climbed 17→18→19 as it appeared (dynamic load/unload of the ref list).
- `PO3_SKSEFunctions.GetActorsByProcessingLevel(0)` returned 14 actors per tick in the same area where `GetNthRef`
  found 1-2. Processing level 0 = high (nearby, combat-active).
- `FindRandomActorFromRef()` is truly random (any actor in range, no direction/hostility); sampling 30+ times and
  filtering by `GetHeadingAngle()` (±60°) is how you approximate "what I am looking at".
- `GetCombatTarget()` returns an actor only in active combat, `None` for a passive nearby enemy.

## No Papyrus raycast

There is no raycast in Papyrus. A script cannot find where a beam or projectile meets the terrain, so continuous
terrain-impact effects keyed to a beam are not achievable from script alone. Use engine projectile collision (impact
data sets, explosions) instead.

## VM memory and page policy

- Signature (CrashLoggerSSE): `EXCEPTION_ACCESS_VIOLATION` in `SkyrimScript::HandlePolicy::Func4`, through
  `BSScript VirtualMachine -> NativeFunctionBase::Call`, with `SimpleAllocMemoryPagePolicy` (often PapyrusTweaks too)
  in the stack. That is the VM's internal page policy faulting, **not** machine RAM exhaustion; the last script line is
  incidental because the policy serves every script.
- **On a very heavy modlist do not shrink the Papyrus memory page sizes.** A large pool
  (`iMaxAllocatedMemoryBytes`) with small `iMaxMemoryPageSize`/`iMinMemoryPageSize` produces hundreds of thousands of
  tiny pages, which was pathological and crashed to desktop on game load. Big pages compensate for a big pool; the two
  are coupled.
- The only low-risk lever when crash frequency is intolerable is PapyrusTweaks' `bIgnoreMemoryLimit` true→false, which
  re-imposes the ceiling so the VM freezes or dumps instead of growing into the fault — without touching page geometry.

## Debug output

- `Debug.Notification()`: Skyrim shows **one notification at a time** with ~5 s before the next; notifications from
  rapid script execution pile up and appear minutes later. Not usable for real-time feedback or timing-sensitive tests.
- `Debug.MessageBox()` is **non-blocking** in Papyrus: it does not wait for OK.
- `Debug.Trace()` writes straight to the Papyrus log with no queue delay. Use `[TAG]` prefixes for grepping and
  `Utility.GetCurrentRealTime()` for timing.
- Activating a Lesser Power repeatedly spawns **multiple ActiveMagicEffect instances**, each with its own thread, so
  polling loops from several activations overlap. A GlobalVariable lock is the standard re-entrance guard: read it,
  return if non-zero, set it, work, clear it.

## Reading decompiled source

Decompile with the tool the install has; `scripts\esp\pexdis.py` disassembles a `.pex`, and the mod's own
`scripts\source\*.psc` is better when it exists. Traps in decompiled output (Champollion is what the source used):

- Some blocks decompile as **empty if/elseif branches** with only debug line comments. The assembly output shows genuine
  `jmp` instructions with no code between them, which usually means the original blocks were empty (code commented out
  before compilation), not that the decompiler failed.
- Decompilers can emit **variable shadowing that the compiler rejects**: an inner `Float cosi` against an outer
  `Float cosI` — Papyrus is case-insensitive, so remove the inner redeclaration.
- `OnPlayerFastTravelEnd` declared on an ActiveMagicEffect compiled in the original toolchain but is rejected as
  "Non-native scripts cannot define new events"; removing the event is safe when `OnEffectFinish` handles cleanup.
- Compiling a script that uses another script's type as a property needs a **compilation stub** for that type (minimal
  function signatures), deleted afterwards.

## Third-party APIs named here

`PO3_SKSEFunctions`, `PapyrusUtil`, `DbSKSEFunctions` and similar are SKSE plugins, not vanilla. Their functions are
real only when the DLL is installed and loaded on this runtime — `papyrus-reference` says how to check a pairing. A
declaration in a `.psc` proves nothing about the runtime (the `IsActorBlocking` case).

One example of what such a plugin can add, because it changes what is diagnosable: a projectile-inspection API that
returns the refs a projectile hit, the collision layer names it crossed, and who fired it, and that can set a
projectile's collision radius at runtime. It needs the projectile's **ObjectReference**, not the base form — and it is
how beam pass-through and "who did this damage" questions get answered when Papyrus alone has no raycast.

Source: adapted from skyrim-ai-assistant-toolkit (c) 2026 WingedGuardian, MIT License.
