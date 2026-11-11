# VR scripting, input, weapons (SE/AE: not applicable)

The half of VR that a script touches: player control, controller input, movement, weapons, hit detection, and testing
with a user in a headset. Engine/build differences are [vr-differences.md](vr-differences.md); general Papyrus semantics
are [papyrus-runtime.md](papyrus-runtime.md). **None of this applies to SE or AE.**

## Player control

- **`DisablePlayerControls()` does not prevent VR thumbstick movement.** VR controller input is a separate engine-level
  input system that bypasses the traditional control-disable flags, so during a scripted sequence the player walks
  around anyway.
- The combination that works: `DisablePlayerControls(True, True, False, False, False, True, True, False, 0)` **plus**
  `Actor.SetDontMove(True)`. `SetDontMove` is the key — neither call alone stops VR movement. Source: a decompiled
  effect script from a working VR mod, confirmed in game by the source's author.
- `Actor.SetRestrained(true)` was tried and is **not** effective for VR movement: it operates at the actor level, not
  the input level. READ (CK wiki): "disables player movement, camera switching and camera rotating". Confidence 85 % in
  the source.
- `Game.SetPlayerAIDriven(true)` can be combined for belt and braces — AI behaviour overrides player control.
- Over-encumbrance only slows the player to walk speed; it does not prevent movement.
- Paralysis works but triggers ragdoll physics — avoid it for cinematic sequences unless a no-ragdoll paralysis mod is
  installed.
- `ForceActorValue("SpeedMult", 0)` prevents movement but feels unresponsive (input still registers, the character just
  does not move).
- VR-native options (VRIK Actions, an input-disabling SKSE plugin) work best and cost a dependency.
- `EnablePlayerControls()` is still needed to restore menu/combat input; pair it with `SetRestrained(false)`.

## Immobilising while keeping the fight

- `DisablePlayerControls(movement)` makes the player effectively un-attackable — NPCs stop aggroing.
- To immobilise the player and **keep aggro**, use `Actor.SetDontMove(true)` **alone**: it freezes thumbstick
  locomotion without freezing the VRIK weapon-bone aim, so the player can still fight.
- `SetRestrained` stops movement and not attacks.
- To freeze an NPC victim completely (no movement, no attacks) use `EnableAI(false)` — and restore AI before any kill,
  or the corpse despawns (see the `OnEffectFinish` guard in [papyrus-runtime.md](papyrus-runtime.md)).

## Weapon draw state

- **`DisablePlayerControls(abFighting=true)` sheathes the weapon** when `EnablePlayerControls` is called afterwards: the
  engine resets the drawn state when the fighting flag is toggled.
- To freeze the player while preserving a drawn weapon, leave fighting enabled:
  `DisablePlayerControls(true, false, false, false, false, false, true, false, 0)`, combined with `SetDontMove(true)`
  for the thumbstick freeze.

## Moving the player

- **`SetPosition()` on the player triggers a cell reload in VR** — a loading screen even for a short distance. Never use
  it for teleportation.
- `TranslateTo()` at very high speed (100,000+) is effectively instant and does **not** trigger a cell reload; the
  camera follows smoothly and at that speed the movement is imperceptible. This is the working flash-step.
- `MoveTo()` on the player behaves like `SetPosition()` and triggers the reload; avoid it for short movements.
- `Game.FadeOutGame()` + `SetPosition` is the worst option: a multi-second black screen followed by landscape
  flickering as assets reload.

## Controller input: the SKSE Input API does not work here

- `Input.GetMappedKey("Right Attack/Block")` returns **-1**: VR controllers are not mapped through DirectInput
  keycodes. `GetNumKeysPressed()`/`GetNthKeyPressed()` never see them, and `IsKeyPressed()` is useless for a VR
  trigger, grip or button. Only `GetMappedKey("Left Attack/Block")` returned a value (507) in the source's testing.
- **The VRIK script's native globals are the API that works** (`Data/Scripts/VRIK.psc`, all native, all globals). Pass
  `false` for the right hand, `true` for the left. Confirmed on a standalone headset through streaming and
  OpenComposite:
  - `VRIK.VrikIsTriggerPressed(bool onLeft)` — clean press/release, no false positives;
  - `VRIK.VrikIsGripPressed(bool onLeft)`;
  - `VRIK.VrikIsThumbstickPressed(bool onLeft)`;
  - `VRIK.VrikIsButtonAPressed(bool onLeft)`, `VrikIsButtonBPressed(bool onLeft)`;
  - `VRIK.VrikGetHandX/Y/Z(bool onLeft)` — world-space hand position, live;
  - `VRIK.VrikGetHmdX/Y/Z()` — world-space HMD position;
  - `VRIK.VrikGetAxisX/Y(bool onLeft)` — thumbstick axes;
  - `VRIK.VrikGetControllerType()` — a Quest 3 reported as 0 (Rift/Oculus).
- **Use `Pressed`, not `Touched`.** `VrikIsTriggerTouched(false)` returned TRUE at rest: a finger resting on a
  capacitive trigger is enough.
- `VrikGetFingerPos` has a **signature mismatch** against the current VRIK VR build and will not bind; every other
  function above works. The duration functions (`VrikTriggerPressDuration` and friends) were not tested.

Direction from the hand to the body (horizontal, good enough for extension or projectile aiming):

```papyrus
float dx = VRIK.VrikGetHandX(false) - player.GetPositionX()
float dy = VRIK.VrikGetHandY(false) - player.GetPositionY()
float dist = Math.sqrt(dx*dx + dy*dy)
float sinAng = dx / dist
float cosAng = dy / dist
```

- **VRIK's "Adjust Held Weapon Positions" option tilts held weapons to sit better in the hand, which deflects a
  concentration beam's origin by ~15°.** For a staff firing a beam it fires noticeably off-centre; disabling that option
  makes the beam follow the controller direction exactly. It is a per-save MCM setting, not an `vrik.ini` value.

## Weapons at runtime: what works and what does not

Confirmed in VR by the source's author:

- **A direct swap works**: `UnequipItem(weaponA, false, true)` then `EquipItem(weaponB, false, true)` changes the mesh
  in hand. But force-swapping the player's equipped weapon is bad practice — it stutters and it takes the choice away
  from the player. Check that the required weapon is equipped and refuse activation instead.
- **`NetImmerse.SetNodeScale(actor, "WEAPON", scale, false)` works** for instant weapon scaling, with
  `QueueNiNodeUpdate()` after it. One call to extend, one to retract, no per-tick work, engine renders at framerate.
  A visible weapon must be equipped.
- `Weapon.SetReach()` is respected by the game independently of the mesh but **only from a game restart** — during
  gameplay the value changes and hit detection does not (see [records-and-plugins.md](records-and-plugins.md)).
- `Weapon.SetModelPath()` does **not** change an equipped weapon's visual, even through unequip → set → re-equip.
- `Weapon.SetEquippedModel()` was **destructive**: no visual change, then the weapon vanished from the hand and only an
  unequip/re-equip recovered it. Never use it.
- `ModActorValue("SpeedMult", -70)` has **no effect** on VR thumbstick locomotion; `ModActorValue("CarryWeight",
  -99999)` does slow it via over-encumbrance. Use the second when a slowdown is the goal.
- An effect shader fetched by FormID came back `None` (`GetFormFromFile(...) as EffectShader`) — either the FormID or
  the cast was wrong; verify the form type before concluding the API is broken.

## Weapon reach and collision in VR

- **The WEAP Reach field does not control VR weapon collision distance.** HIGGS/VRIK use the mesh's Havok physics
  collision geometry, not the Reach value.
- Extending collision means editing the NIF: a longer convex shape, or a chain of physics bones with constraints
  (one working example used a 17-bone chain). A standard weapon uses a box shape matching the visual mesh. A dummy
  armour trick does not extend reach on its own.
- VR melee hit detection is **layered**: vanilla engine + HIGGS + an optional weapon-collision plugin + an optional
  active-ragdoll plugin. A hit can come from any layer, and a weapon-collision plugin's own enemy-detection range
  (default 600) is often the real bottleneck — raise it before blaming the weapon.
- **The engine's melee hit range is effectively capped (~1500 game units) and does not scale with a longer collision
  capsule.** Reach beyond that cap has to come from a script (a per-swing scan plus a damage or spell cast), not from
  enlarging the capsule.
- Havok units: **1 Havok unit ≈ 70 game units**, and that applies to `bhk*` collision blocks only. A ~5,000-game-unit
  collision shape is ~71 Havok units; getting this wrong puts the collision geometry far from the visual mesh.
- Vanilla reach without a collision mod: `141 (fCombatDistance) × NPCScale × WeaponReach` — 10.0 ≈ 1,410 units ≈ 21 m,
  50.0 ≈ 7,050 units ≈ 106 m. The source's framework table and its reach section disagree about whether Precision
  exists for VR; treat HIGGS/VRIK as the collision owners and check the mod page (see
  [vr-differences.md](vr-differences.md)).

## `OL_WEAPON` projectile routing

- Any projectile that physically contacts a Havok collision shape on layer `OL_WEAPON` (layer 5) has its damage routed
  to the **weapon's owner-actor**. This is engine-level and happens before spell absorption, magic resist, blocking and
  every script event: none of those can intercept it.
- Consequence: a weapon mesh with a long capsule on that layer makes the player take full spell damage from any
  projectile touching any part of it, however far from the hand.
- Paths that do **not** fix it (confirmed dead ends): `ModActorValue("SpellAbsorption", …)` — not a valid actor value,
  errors on every call, and absorption gates the spell-cast-at-actor path, not collision routing; a `MagicResist` buff,
  an absorb MGEF or the Atronach Stone perk (same wrong path); a projectile-hit event from a plugin that does not
  export it on VR.
- A weapon-collision plugin that uses hardcoded per-weapon-type reach (sword ≈ 90, greatsword ≈ 100, axe ≈ 70 game
  units) reads neither the mesh nor the record, so it cannot see a long capsule.
- The workable design answer: frame the extra vulnerability as the trade-off. Extending the blade exposes the player;
  retracting it restores normal hit detection.

## PLANCK (VR melee hit detection) — an external plugin

- Config: `Data/SKSE/Plugins/activeragdoll.ini`; the script `planck.psc` (`ScriptName PLANCK Hidden`) ships its source
  in `Data/Source/Scripts/` — a **different** folder from `Data/Scripts/Source`, so a compiler needs it on its import
  path.
- `PLANCK.GetSetting(string)` / `PLANCK.SetSetting(string, float)` read and write any numeric INI setting at runtime.
  `GetSetting` returns exactly `-2.71828` for an unknown name, which is the typo check.
- Hit-speed gates, read **per hit** (so `SetSetting` takes effect live, no restart): `hitSwingSpeedThreshold`
  (default 5.0), `hitStabSpeedThreshold` (2.5), `hitRequiredHandSpeedRoomspace` (1.5 — a weapon walked into an enemy
  without hand movement does not register).
- Setting all three to `0` makes any contact register a melee hit. It is a global setting, so a per-weapon effect means
  toggling it from the weapon's script and restoring it on exit. This is the engine-native "damages on any touch" fix:
  collision runs at engine framerate, with no script sampling gap.
- Also exposes `AddIgnoredActor`, `GetLastHitNodeName` (call inside `OnHit`) and aggression-topic setters.

## Third-party APIs in VR

- `miscutil.ScanCellNPCs()` (PapyrusUtil) **crashed the DLL in VR** with an access violation in
  `TESObjectREFR::SetParentCell` while processing actors with a missing cell reference (e.g. a goat with
  `ParentCell: ---`). A `FindRandomActorFromRef()` loop is the safer replacement.
- `papyrusutil.ObjRefArray()` works in VR for arrays beyond the 128-item default (tested to 270).

## Testing anything the user has to see in a headset

- **Narrate on the HUD.** The user cannot read chat while wearing the headset: drive every instruction and countdown
  through `Debug.Notification`, and only ask them to take it off when the HUD says the sequence finished.
- **Burst, never single-shot.** A one-off effect is a shooting star. Fire 10-15 times over ~10 s so one burst is one
  unmissable observation.
- Prefer explicit player facing or angles over weapon-node geometry when the test does not need the weapon: it removes
  pose dependency.
- Log results to a file and read them yourself. Do not rely on the user's eyes, and prefer a Papyrus channel or an
  on-disk log over console capture.
- A headless session has no usable player body (on one install the emulated headset pose lay on the floor), so **never
  use the player as attacker, target or hit recipient** in an automated test: spawn dedicated test actors, record their
  identities, and keep the player only to hold the area loaded.

Source: adapted from skyrim-ai-assistant-toolkit (c) 2026 WingedGuardian, MIT License.
