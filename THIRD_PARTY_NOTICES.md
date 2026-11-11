# Third-party notices

SkyrimTools ships no binaries. The entries below are code or text adapted into this repository, and tools that
`setup.cmd` downloads (pinned by SHA-256) into `%SKYRIM_TOOLS_HOME%`, outside the repository.

## Adapted into this repository

### skyrim-ai-assistant-toolkit

- Source: https://github.com/WingedGuardian/skyrim-ai-assistant-toolkit (commit 206de46, 2026-11-05)
- License: MIT, Copyright (c) 2026 WingedGuardian
- Adapted: `scripts/logs/crash_triage.py`, `scripts/logs/papyrus_triage.py`, `scripts/logs/skse_load_status.py`,
  `scripts/logs/mirror_logs.py`, `scripts/logs/_paths.py`, `scripts/save/ess_scan.py`, `scripts/save/cosave_info.py`,
  `scripts/esp/espdiff.py`; the knowledge in `skills/skyrim-engine-knowledge/` and `skills/skyrim-troubleshooting/`;
  the DevBench facts in `skills/skyrim-live-game/`.

```
MIT License

Copyright (c) 2026 WingedGuardian

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Downloaded by setup.cmd (not in this repository)

| Tool | Source | License | Pin |
|---|---|---|---|
| houseCARL | https://github.com/Avick3110/houseCARL | see its release | release tag, SHA-256 from the release digest |
| papyrus-compiler | https://github.com/russo-2025/papyrus-compiler | MIT | 2026.03.15, SHA-256 in `setup.ps1` |
| SkyLink AI (`-SkyLink`) | https://github.com/jarvann/SkryimMCM | MIT | v1.0.0, SHA-256 in `setup.ps1` |
| Ghidra, Temurin JDK, pyghidra-mcp (`-Ghidra`) | NSA Ghidra, Adoptium, PyPI | Apache-2.0 / GPLv2+CE / see PyPI | `setup.ps1` and `requirements-re.txt` |

SkyLink AI's console-command code is itself adapted from ConsoleUtilSSE by VersuchDrei (MIT), as its README says.
