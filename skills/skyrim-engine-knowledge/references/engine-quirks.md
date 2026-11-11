# Engine quirks and vanilla patterns

Behaviour of the engine and of the vanilla content that is not in a record's field list. Papyrus semantics are
[papyrus-runtime.md](papyrus-runtime.md); VR-only behaviour is [vr-differences.md](vr-differences.md).

## Prefer the native engine mechanism

"Simple" in modding means simple **from the engine's perspective**, not simple as code. The first question about any
mechanic is "how does the game already handle this?", and the answer is the implementation. Papyrus is a supplement to
engine behaviour, never a replacement for it.

| Problem | Wrong (script hack) | Right (native) |
|---|---|---|
| Stagger immunity | `ForceActorValue("Stagger", 0)` every tick | a perk with a stagger-resist entry point |
| Keeping magicka up | `RestoreActorValue("Magicka", 9999)` in a loop | an enchantment with 0 magicka cost |
| Preventing melee auto-fire | dispel inside `OnEffectStart` | strip the enchantment from the weapon form |
| Hit detection | a Papyrus raycast (which does not exist) | engine collision (projectile, weapon, impact data) |
| Movement restriction | script-forced positions | `SetRestrained`, paralysis, `SetDontMove` |

## Vanilla-aligned mechanics: stagger and bleed

Vanilla is the frame of reference. An invented mechanism that "looks right" usually has no animation, no damage routing
or no build-up, and the vanilla path is the one the engine supports.

| Mechanic | Wrong (invented) | Vanilla-aligned |
|---|---|---|
| Bleed on hit | a ValueModifier MGEF on a Concentration enchantment | a Fire-and-Forget bleed spell cast per swing (mirrors the Bleeding Strikes perk) |
| Script stagger | a Stagger-archetype Fire-and-Forget spell cast from Papyrus | `PushActorAway(target, 1-3)` — a physical stumble, proven engine behaviour |
| Stagger immunity | `ForceActorValue("Stagger", 0)` polling | a perk with a ModIncomingStagger ×0 entry |
| Melee auto-fire prevention | dispel in `OnEffectStart` | strip the enchantment from the weapon form |

- **A Stagger-archetype spell cast from Papyrus produces no visible stagger.** `Spell.Cast(source, target)` on a spell
  wrapping a Stagger MGEF shows no animation, because vanilla staggers come from perk entry points on a weapon hit,
  shout impact data, or spell impact data on projectile collision — none reachable from a `Spell.Cast()` call. Do not
  pursue it; `Caster.PushActorAway(target, 1.0-3.0)` reads as a stagger and fires reliably from script.
- **A Stagger MGEF on a Concentration enchantment is a stagger lock.** It re-fires at ~90 Hz in VR, so the animation
  restarts before it completes: an infinite locked stumble. Never put a Stagger MGEF on a Concentration enchantment;
  deliver stagger per swing from script.
- **The vanilla bleed pattern** (`0C367A:Skyrim.esm`, the Bladesman perk's effect): ValueModifier/Health,
  FireAndForget, duration > 0 (it ticks after application), delivered by a perk entry point on each weapon swing hit.
  The script analogue for a beam or sweep weapon is one Fire-and-Forget bleed cast per swing per actor on the line,
  from a per-swing scan gated on the direction having changed.

## Known vanilla bugs

- `IsHostileToActor` **crashes to desktop** when passed a NONE object.
- The `abPreventEquip` flag does not work on NPCs (ammo only).
- `ForceThirdPerson`/`ForceFirstPerson` cannot report the current camera mode, and a forced view change reverts
  immediately.
- Melee bashing costs no stamina in Skyrim VR, which is an infinite stagger exploit.
- `GetActorValue("IsBlocking")` errors on every call and is not an actor value — see
  [papyrus-runtime.md](papyrus-runtime.md).

## ImageSpace (post-processing) from script

- Vanilla `Skyrim.esm` IMODs: `FadeToBlackImod` `0x0F756D`, `FadeToBlackHoldImod` `0x0F756E`,
  `FadeToBlackBackImod` `0x0F756F`.
- `Apply(strength)` snaps to the effect; `ApplyCrossFade(strength)` transitions gradually. The hold IMOD at partial
  strength (e.g. 0.6) dims the screen instead of blacking it out.
- In VR the post-processing choice fights the UI: off fixes some UI problems and creates a visible seam between the
  eyes, on fixes the seam and breaks UI in some configurations.

## Capability spells

- An ability is an "always on" spell: Constant Effect, no duration.
- `AddSpell` on an ability the actor already has is a safe no-op (no stacking), and abilities persist through
  save/load — remove them explicitly when the effect should end.

## Papyrus INI keys that matter on a heavy modlist

- `fUpdateBudgetMS` (default 1.2 ms per frame, all scripts combined) is the budget; with 700+ plugins it is frequently
  exceeded. `iMaxOpsPerFrame` is the per-task operation count (vanilla 100).
- PapyrusTweaks keys worth knowing: `iMaxOpsPerFrame` (raise it), `bDisableMissingScriptError` and
  `bDisableNoPropertyOnScriptErrorLogs` (suppress cosmetic version-skew noise), `bSpeedUpNativeCalls` (decouples native
  calls from framerate — a real performance win), `iStackDumpTimeoutMS` (lower it so a stack dump fires before a freeze
  times out and the offending stack is actually captured), `bDisableMissingScriptError` for orphan noise,
  `bIgnoreMemoryLimit`.
- The inflated Papyrus memory settings on a very heavy modlist are load-bearing: read the VM page-policy note in
  [papyrus-runtime.md](papyrus-runtime.md) before changing any `iMax*Memory*` value.

## A mod's MCM Helper settings file can override its SKSE INI

MEASURED on one install: a mod configured through MCM Helper kept `Data/MCM/Settings/<mod>.ini` beside its
`Data/SKSE/Plugins/<mod>.ini`. Changing a key only in the SKSE INI left the mod's startup log reporting the old
behaviour until the same key was changed in the MCM settings file too. **When a mod has both files, edit both with the
game closed, and confirm the change from the mod's own log line, not from the file you edited.**

## Version-sensitive SKSE plugin traps

**These are observations on one install with dates, not properties of the plugins. Re-check the changelog before
acting, and keep a personal "do not update past X" list.**

- **A Papyrus fix-up plugin's newer build broke NPC dialogue in VR.** Observed: version 4.1.1 (Oct 2025) caused NPC
  dialogue options never to appear — the NPC speaks the greeting and the choice menu does not open — with many
  `Unbound native function` and `does not match existing signature` lines at load time; its validation and
  call-attempt hooks were implicated. The stable 2023 build was the fix. Do not treat "newest" as "best" for a fix-up
  plugin on VR.
- **Papyrus Extender updates can break backward compatibility.** Observed: a March 2025 update changed signatures in
  the plugin's own script class, so mods compiled against older versions failed with
  `does not match existing signature` (`GetSkinColor`, `GetHairColor`, `GetAllSpellsInMod`, `ToggleChildNode`,
  `ResetActor3D` among them). A DLL and the `.psc` declarations its consumers compiled against move together.
- **The DLL on disk is the source of truth for "what version is installed", not the mod manager.** Read the embedded
  File/Product version of `Data/SKSE/Plugins/*.dll`; a manually installed or hand-reverted plugin is invisible to
  Vortex/MO2, so the manager's version can disagree with what the game loads. Because these carry no save data,
  reverting one mid-playthrough is safe — the problem disappears on the existing save.
- **Engine-fix plugins that exist and what they are for:** an Engine Fixes port (tree LOD visibility, BSFadeNode offset
  corrections, volume settings persistence), a Poached Bugs port (Scrambled Bugs fixes for spellcasting, textures and
  weapons), and a Papyrus Tweaks build (script execution fixes, VR playroom script pausing — see the version trap
  above). Some ship a second, user-owned TOML beside the one they install (`EngineFixesCustom.toml` next to
  `EngineFixes.toml`), which is where overrides belong.

## Live-game probing: the server is not the game

Measuring anything in a running game needs a probe that survives the stall you are trying to detect. The bridge tools
themselves — and their read/write safety rules — are `skyrim-live-game`. LESSONS MEASURED by the source's author through
such a bridge (an external tool, not shipped here):

- A live bridge runs on **its own thread**, so a deadlocked, hung or paused game still answers a ping. **A ping is not
  proof the game is alive.**
- A probe dispatched onto the **main thread** fails with a timeout in exactly the case it exists to detect.
- A health endpoint answered off the main thread distinguishes four states, and the frame counter alone does not: frame
  advancing = running; frame frozen with an empty task queue = **paused, console open or loading, not a hang**; frame
  frozen with tasks pending and no task progress = **hung**; no save loaded = main-menu state.
- Identity fields (pid, port, exe, runtime) tell you **which instance answered** — with two games running, a client on
  the wrong port returns real-looking answers from the wrong game.
- Status codes carry meaning: a timeout/gateway error means the main thread is busy or stuck while the server is fine;
  a bad-argument error means the request shape is wrong; connection refused means the game is closed. Collapsing these
  into "it failed" sends you debugging the wrong layer.
- **A successful read is not a running game.** A modal message box pauses the simulation while every read still
  succeeds. Before a baseline or any timing, check for an open menu or message box and confirm the frame counter
  advances.
- **Write actions while paused queue** and do not process; read actions work. A write that "succeeded" during a pause
  has not happened yet.
- Driving a save through a bridge hung the main thread once (a 0-byte `.ess.tmp` that never finalised, forcing a
  kill); piping a load or save through the game's own UI never hung. Treat a bridged save as suspect and prefer the
  user's own save/load until you have verified otherwise on that build.
- Heavy console commands can crash a large load order on their own (a full physics `reset` did, reproduced by hand), so
  keep live commands light and targeted, and get the user's agreement and a save before any state change.

## Reading these observations correctly

Version numbers, plugin names and measured dates in this file describe **one install at one time**. The mechanics
("masters move together", "a duplicate native is a stale plugin") are the durable part; the specific builds are not.

Source: adapted from skyrim-ai-assistant-toolkit (c) 2026 WingedGuardian, MIT License.
