---
name: nexus-api-search
description: >-
  Preferred way to search and read Nexus Mods without a browser: the public GraphQL API at
  https://api.nexusmods.com/v2/graphql, anonymous, no API key. Use it first for finding a mod by name or by words in its
  description, reading a mod's full description, requirements, tags, version and file list, checking a keyword / Papyrus
  function / permission text on a mod page, or finding a mod's GitHub source link. nexusmods.com pages (WebFetch, the
  web-fetch agent) answer 403 to bots, and WebSearch snippets are thin; this API does not. Load before any Nexus lookup.
---

# Nexus lookups through the GraphQL API

Use this **before** WebFetch / WebSearch for anything on nexusmods.com. houseCARL's Nexus tools are the alternative when that
MCP server is connected; this works when it is not (and needs nothing installed).

## Fast path: the script
`python $SKYRIM_TOOLS_REPO\scripts\misc\nexus_gql.py <cmd>` (stdlib only; any Python 3). Output is UTF-8.

| Need | Command |
|---|---|
| find mods by name | `search "summoned swords" [--count 10] [--sort downloads\|updatedAt\|endorsements\|relevance]` |
| mods whose **description** contains a word | `grep "WeaponTypeBoomerang"` |
| name, author, version, dates, counters, tags, requirements | `mod 99230` |
| full description, BBCode stripped (`--raw` keeps markup) | `desc 99230` |
| files with category (MAIN / UPDATE / OLD_VERSION / ARCHIVED …) and notes | `files 99230` |
| any other query | `raw '{ ... }'` |

`--game <domain>` defaults to `skyrimspecialedition` (id 1704). Other ids known to the script: `skyrim` 110, `skyrimvr` 2698,
`fallout4` 1151, `starfield` 4187; add more to `GAME_IDS` (find an id with `game(domainName:"…") { id }`).

## Raw API facts (verified 2026-11-04)
- `POST https://api.nexusmods.com/v2/graphql`, header `Content-Type: application/json`, a browser-like `User-Agent`, body `{"query":"…"}`.
  Anonymous; no key. Introspection works (`__type(name:"Mod") { fields { name } }`, `__schema { queryType { fields { name } } }`).
- `mod(gameId: Int, modId: Int)`: name, author, uploader{name}, summary, **description** (BBCode, includes modder docs, keywords,
  Papyrus API, GitHub links), version, createdAt/updatedAt, downloads, endorsements, tags{name}, adultContent,
  `modRequirements { nexusRequirements { nodes { modName notes } } dlcRequirements { gameExpansion { … } } }`.
- `modFiles(gameId, modId)`: name, version, category, date (unix), sizeInBytes (string), fileId, description.
- `mods(filter:{…}, sort:[…], count:, offset:)` returns `{ totalCount nodes {…} }`. Filter fields are **lists** of `{value, op}`:
  - `gameDomainName:[{value:"skyrimspecialedition"}]` — always include it, or results span all games.
  - `nameStemmed:[{value:"text", op: MATCHES}]` — stemmed name search (use this for name lookup).
  - `description:[{value:"text", op: MATCHES}]` — word search inside descriptions (found `WeaponTypeBoomerang` → mod 182872).
  - `name` takes `EQUALS` / `WILDCARD` only; a `*text*` wildcard returned nothing, prefer `nameStemmed`.
  - others: `author`, `uploader`, `tag`, `categoryName`, `updatedAt`, `createdAt`, `downloads`, `endorsements`, `adultContent`.
  - sort: `[{downloads:{direction:DESC}}]` (also `updatedAt`, `endorsements`, `createdAt`, `relevance`, `name`, `size`).
- Other root queries seen: `modsByUid`, `modFilesByUid`, `modFileContents` (archive contents), `fileHash(md5)`, `tags(gameId)`,
  `categories(gameId)`, `collectionsV2`, `users`, `userByName`, `news`, `comment`/`searchComments`. Introspect before relying on them.
- Errors come back as `{"errors":[{"message":…}]}` with HTTP 200 — the message names the wrong field/enum, fix and retry.

## Working rules
- A description is the author's own text: it states keywords, API names and requirements, but also drifts out of date.
  Quote it with the mod id and `updatedAt`, and say when something was read only from the description and not tested.
- Read **permissions** text (reuse / redistribution) before copying anything from a mod; the API description may not carry the
  Permissions tab, then say it is unverified. Many authors link a GitHub repo in the description: check its license
  (`https://api.github.com/repos/<owner>/<repo>` is also anonymous, rate-limited to 60 requests/hour).
- Downloading files is not available anonymously (needs the user's login / premium); the API gives metadata and text only.
  The user downloads archives; unpack them per `skyrim-modding-practices` (own empty folder, `python -I`).
- Be polite: one query per question, `count` small, no crawling.
