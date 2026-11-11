# Release review: gate a mod release before publishing

A review procedure for a mod you (the user) are about to publish — plugin, script, mesh, asset or SKSE-DLL mod, first
release or update. It reviews **only what changed since the last published version**, changes nothing while reviewing,
and brings every finding to the author before any fix.

**Why it asks before it fixes.** A mod's correctness is judged in the game, by its author, and the reviewer cannot see
in-game behaviour. A review that runs after the author has tested and then "fixes" something that only *looks* wrong can
publish a broken mod that was working. Every rule below follows from that.

**Words used here.** *The author* = the user publishing the mod. *Players* = people who install it. *Author-tested* =
behaviour the author observed in game for this version.

## The rules

1. **Read-only review.** While reviewing, change nothing in the mod, the game install or the package — no fixes, no
   cleanups, no "while I'm here". Exports and decompiles for reading go to a scratch folder.
2. **Every finding goes to the author, including definite ones.** No silent fixes, and no finding dropped because it was
   judged minor.
3. **What the author saw in game outranks the reviewer's reading of the files — for what they actually saw.** If the code
   reads as X and the author observed Y, the reading is the suspect. But testing covers only the behaviour observed, on
   the author's install, with the build they ran. It does not cover packaging, dependencies, other load orders or a
   fresh install.
4. **Nothing is fixed without the author's individual approval.** Suspected findings are confirmed one at a time.
5. **A fix to an author-tested area makes that testing stale.** Say so each time, and name the re-test.

Recommend running the review **before** the author's final in-game test pass, so approved fixes get tested by that pass;
ask which they want.

## Two kinds of finding

| Kind | Means | Examples |
|---|---|---|
| **DEFINITE** | provable from the files alone, no in-game behaviour involved | a script fails to compile; a master the plugin needs is not a stated requirement; a file the installer names is missing; an asset that must not be published is inside the package |
| **SUSPECTED** | depends on how the game behaves at runtime | a timing, condition, property or record that *looks* wrong |

Use those two words consistently in everything shown to the author, and label each finding's evidence **MEASURED /
READ / INFERRED / ASSUMED**.

## Phase 0 — baseline: what players already have

Scope is the **difference between what was last published and what will be published now**, never the whole mod.

Baseline, in order of preference: the release record of the previous version (Phase 6 writes it); **the archive players
actually downloaded** (the published bytes, not development files); a git tag known to match what was published; none of
these (first release) → the whole package is in scope.

Tell the author which baseline was used and how much changed, and **get them to confirm it before reviewing** — a wrong
baseline quietly shrinks or inflates the review.

How to diff each file type:

- Plugin (ESP/ESM/ESL): a text round trip of both sides, or `python scripts\esp\espdiff.py diff OLD.esp NEW.esp` for the
  added, removed and changed records and their subrecords.

- `.pex`: decompile/disassemble both sides (`scripts\esp\pexdis.py`, or the shipped `.psc`). **The shipped `.pex` is what
  players' games run**, not the `.psc`.
- Text (`.psc`, INI, JSON, FOMOD XML): diff directly.
- Binary with no text form (NIF, audio, DLL): changed = hash differs; review that file through its tool.

## Phase 1 — ask what the author tested, before judging anything

Ask, in one short message:

- which features they tested in game for this version, and what they did not;
- **which build they tested** — is it byte-identical to what will be published? Testing a development plugin, or loose
  files that will ship inside an archive, does not test the published bytes;
- anything they already know is rough.

Record the answer as the **author-tested set** and tag each changed area tested or untested.

## Phase 2 — read the changes

Read every changed or added file **in full**, for context. **Findings are scoped to the changed lines and what they
affect.** Something wrong in an unchanged file that you notice anyway is reported as **PRE-EXISTING**, listed separately,
and does not block the release: players already have it, so holding the release does not fix it. **Exception:** an old
defect this release makes players REACH — through a new feature, a new default or a new line in the description — is
treated as in-diff.

## Phase 3 — the checklist (only the rows the diff touches)

| Check | How |
|---|---|
| Shipped `.pex` matches the `.psc` it claims to be | disassemble the shipped `.pex` and compare with the source |
| Scripts compile | `python scripts\papyrus\papyrusc.py compile X.psc -o <new mod>\Scripts` (skill `papyrus-compiler`) |
| **Did the author's testing exercise THIS mod's record?** | ask the record layer who wins that FormID on the author's order (`housecarl_check`/`housecarl_records`). If another plugin wins it, their test ran the other plugin's version |
| Dependencies another install may lack | the plugin's masters; a soft `GetFormFromFile` dependency on another mod's forms (returns `None` silently when that mod is absent); required SKSE plugins at a compatible build and minimum version. **The author's own install has all of these, so their testing cannot catch this class** |
| Properties | non-auto properties stay blank after load; added, removed or renamed properties against the plugin's VMAD |
| Save compatibility for players mid-playthrough | new masters; removed scripts, forms or quests; changed property sets — verdict via the rubric in `skyrim-engine-knowledge` |
| Plugin structure | light-plugin FormID range, FormID reuse, ONAM for ESM overrides |
| Package contents | file list and hashes against the baseline; loose files vs archive; FOMOD paths resolving to the intended `Data/` layout; no source bundle inside the main package |
| Content that must never be published | the author's private or development plugins, and assets they have no right to redistribute. Ask for their list once and record it |
| Leftover development scaffolding | diagnostic logging, disabled test functions, unused globals |
| Meshes | cross-read with an independent parser; no `PreWEAPON`/`PreSHIELD` nodes on VR — see `skyrim-engine-knowledge`'s NIF file |
| SKSE DLL | build for the runtime; built from the source that was reviewed; Address Library dependency stated |
| Claims | version string, changelog and the mod page match the files; every number re-derived |
| Permissions and credits | every asset from another author: permission status and credit line (`scripts\misc\nexus_gql.py desc <modId>` reads the page text, including permissions) |

A live check in the running game happens only if the author offers a session; see the freeze and crash references for
what a live session can and cannot prove.

## Phase 4 — bring findings to the author

Write the complete findings list first, with nothing applied.

- **DEFINITE findings** may be shown together as one list; each still gets its own answer from the author.
- **SUSPECTED findings: one at a time**, one question per finding, never combined. Each states: what and where (file and
  line, or FormID), in-diff or pre-existing, evidence tier; whether it falls in the author-tested set and the direct
  question **"Have you tested this in game? Can you vouch for it?"**; what the reviewer thinks happens **and that it is
  not certain**, plus the cheapest way to settle it; **what could break if it is changed**; and the options:
  *leave it (I vouch for it)* · *fix it* · *I'll test it first* · *investigate more*.

When a suspected finding is in an author-tested area and the evidence is INFERRED or ASSUMED, recommend leaving it and
say so. Record every answer; a finding the author leaves stays left and comes back only if a later release changes that
code.

## Phase 5 — fixes (only the approved ones, one by one)

- Back up the affected files first.
- Smallest change that does it; rebuild (compile, deserialize); diff against the backup and **confirm only the intended
  lines moved**.
- **The fix is itself new, unreviewed change** — review it before it ships.
- Verify what can be verified offline yourself (compile, disassembly diff, record diff, NIF parse), then leave a single
  re-test list for the author to run as one session, naming which tested area each fix touched.

## Phase 6 — publish gate and the next baseline

Nothing is published until **every finding has the author's recorded answer** and the author gives the final go. Then:

1. Build the package and hash its actual contents; those hashes must match the reviewed files.
2. Write the release record **outside the game's `Data/` and outside the package**, in the place the author nominated:
   a manifest of every packaged file with sha256, size and status; the reviewable sources (`.psc`, plugin text form,
   INI/JSON, FOMOD XML); and the review record (baseline used, author-tested set, every finding with its answer).
   Once the package is handed over, treat it as published: record it as the current version and the next baseline.
3. A clean review is necessary, not sufficient. The upload is the author's step.

### Packaging rules

- **One upload folder.** The main archive, every optional archive, any separate source archive, the page description,
  the summary and the changelog text all go in the same release folder with plain names. Give the author one path.
- **No source in the main file.** The main archive holds what goes into `Data/` plus player docs at the top level. An
  SKSE DLL's source is its own download, never a `Source/` folder inside the main archive. If the licence requires the
  source to stay available, tell the author not to archive that download while the DLL ships.
- **Licence notices travel with the DLL**, beside it (not at the top level), with the readme and page text pointing at
  the separate source download.
- Papyrus `.psc` under `Scripts/Source` is mod content, not "source" in this sense, and stays.

## Red flags

- About to edit anything during the review → rule 1.
- "It's definitely broken, I'll just fix it" → present it and wait.
- Dropping a finding because the author "probably tested that" → present it, marked author-tested.
- Two suspected findings in one question.
- Treating the author's testing as cover for a dependency, packaging or save-compatibility finding — their install is not
  a player's install.
- Reviewing the whole mod without telling the author there was no baseline.
- Calling something wrong on a code read when the author has seen it work in game.

Source: adapted from skyrim-ai-assistant-toolkit (c) 2026 WingedGuardian, MIT License.
