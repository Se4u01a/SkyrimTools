<#
.SYNOPSIS
    Check whether SkyrimTools is installed and usable on this machine, for any agent.

.DESCRIPTION
    Prints one line per part: OK, WARN, FAIL or SKIP. Reads the SKYRIM_* user environment variables that setup.ps1
    writes, resolves the defaults of the launchers, and probes what each part needs (houseCARL exe and .NET Runtime 10,
    the MO2 instance, the optional Ghidra workspace, Python, the MCP launchers and the skills). With -Json it prints
    one JSON object instead of the table. With -Fix it ends with the exact commands that repair each gap.

    Exit code: 0 when nothing failed, 1 when at least one FAIL was found.

.PARAMETER Json
    Machine-readable output: one JSON object { repo, checks[], fixes[] }.

.PARAMETER Fix
    Print the repair commands (setup.cmd with the right switches, etc.) instead of only naming the gap.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\agents\doctor.ps1

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\agents\doctor.ps1 -Json -Fix
#>
[CmdletBinding()]
param(
    [switch]$Json,
    [switch]$Fix
)

$ErrorActionPreference = 'Stop'
$Repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

$results = New-Object System.Collections.Generic.List[psobject]
$fixes = New-Object System.Collections.Generic.List[string]

function Add-Result {
    param([string]$Name, [string]$Status, [string]$Detail, [string]$Repair)
    $results.Add([pscustomobject]@{ name = $Name; status = $Status; detail = $Detail; fix = $Repair })
    if ($Repair -and -not $fixes.Contains($Repair)) { $fixes.Add($Repair) }
    if (-not $Json) {
        $color = switch ($Status) { 'OK' { 'Green' } 'WARN' { 'Yellow' } 'FAIL' { 'Red' } default { 'DarkGray' } }
        Write-Host ('  {0,-4} {1,-16} {2}' -f $Status, $Name, $Detail) -ForegroundColor $color
    }
}

function Get-SkyrimVar {
    param([string]$Name)
    $value = [Environment]::GetEnvironmentVariable($Name, 'Process')
    if (-not $value) { $value = [Environment]::GetEnvironmentVariable($Name, 'User') }
    if (-not $value) { $value = [Environment]::GetEnvironmentVariable($Name, 'Machine') }
    if ($value) { $value = [Environment]::ExpandEnvironmentVariables($value) }
    return $value
}

function Get-FileCount {
    param([string]$Path, [string]$Filter)
    if (-not (Test-Path -LiteralPath $Path)) { return 0 }
    return @(Get-ChildItem -LiteralPath $Path -Filter $Filter -ErrorAction SilentlyContinue).Count
}

if (-not $Json) {
    Write-Host ''
    Write-Host "SkyrimTools doctor" -ForegroundColor Cyan
    Write-Host "  repo: $Repo"
    Write-Host ''
}

# ---------------------------------------------------------------- platform and repo
if ($env:OS -eq 'Windows_NT') {
    Add-Result 'platform' 'OK' "Windows $([Environment]::OSVersion.Version)"
} else {
    Add-Result 'platform' 'FAIL' 'not Windows: the launchers, MO2 and the RE scripts are Windows-only' 'Run on Windows 10/11 x64.'
}

$repoFiles = @('AGENTS.md', 'README.md', 'setup.cmd', 'setup.ps1', '.mcp.json', 'scripts\run_housecarl.cmd', 'scripts\re\run_ghidra_mcp.cmd')
$missing = @($repoFiles | Where-Object { -not (Test-Path -LiteralPath (Join-Path $Repo $_)) })
if ($missing.Count -eq 0) {
    Add-Result 'repo' 'OK' $Repo
} else {
    Add-Result 'repo' 'FAIL' ("incomplete checkout, missing: " + ($missing -join ', ')) 'git clone the full repository; do not copy single files.'
}

$repoVar = Get-SkyrimVar 'SKYRIM_TOOLS_REPO'
if (-not $repoVar) {
    Add-Result 'SKYRIM_TOOLS_REPO' 'WARN' 'not set: the skills cannot find the scripts' 'setup.cmd (it writes the variable for this user)'
} elseif ((Resolve-Path -LiteralPath $repoVar -ErrorAction SilentlyContinue).Path -ne (Resolve-Path -LiteralPath $Repo).Path) {
    Add-Result 'SKYRIM_TOOLS_REPO' 'WARN' "points at another copy: $repoVar" 'Run setup.cmd from the copy you want to use; it rewrites the variable.'
} else {
    Add-Result 'SKYRIM_TOOLS_REPO' 'OK' $repoVar
}

# ---------------------------------------------------------------- install root, houseCARL
$home_ = Get-SkyrimVar 'SKYRIM_TOOLS_HOME'
if (-not $home_) { $home_ = Join-Path $env:LOCALAPPDATA 'SkyrimTools' }
if (Test-Path -LiteralPath $home_) {
    Add-Result 'SKYRIM_TOOLS_HOME' 'OK' $home_
} else {
    Add-Result 'SKYRIM_TOOLS_HOME' 'SKIP' "$home_ (does not exist yet)" 'setup.cmd installs the heavy parts there.'
}

$hcExe = Get-SkyrimVar 'HOUSECARL_EXE'
if (-not $hcExe -or -not (Test-Path -LiteralPath $hcExe)) {
    $candidates = @(
        (Join-Path $Repo 'houseCARL\src\housecarl-mcp\bin\Release\net10.0\housecarl-mcp.exe'),
        (Join-Path $Repo 'houseCARL\server\housecarl-mcp.exe'),
        (Join-Path $home_ 'housecarl\server\housecarl-mcp.exe')
    )
    foreach ($cand in $candidates) {
        if (Test-Path -LiteralPath $cand) { $hcExe = $cand; break }
    }
    if (-not $hcExe) { $hcExe = Join-Path $home_ 'housecarl\server\housecarl-mcp.exe' }
}
$hcData = Get-SkyrimVar 'HOUSECARL_DATA_DIR'
if (-not $hcData -or -not (Test-Path -LiteralPath $hcData)) {
    $fallbackData = Join-Path $home_ 'housecarl-data'
    if (Test-Path -LiteralPath $fallbackData) { $hcData = $fallbackData }
    elseif (-not $hcData) { $hcData = $fallbackData }
}
if (Test-Path -LiteralPath $hcExe) {
    Add-Result 'housecarl' 'OK' "$hcExe ($([math]::Round((Get-Item -LiteralPath $hcExe).Length / 1MB, 1)) MB)"
    Add-Result 'housecarl data' 'OK' $hcData
} else {
    Add-Result 'housecarl' 'FAIL' "not found: $hcExe" 'setup.cmd'
}

$dotnet = $null
$cmd = Get-Command dotnet -ErrorAction SilentlyContinue
if ($cmd) { $dotnet = $cmd.Source }
if (-not $dotnet) {
    $candidate = Join-Path $env:ProgramFiles 'dotnet\dotnet.exe'
    if (Test-Path -LiteralPath $candidate) { $dotnet = $candidate }
}
$net10 = $false
if ($dotnet) {
    try { $runtimes = & $dotnet --list-runtimes 2>$null } catch { $runtimes = @() }
    $net10 = @($runtimes | Where-Object { $_ -match '^Microsoft\.NETCore\.App 10\.' }).Count -gt 0
}
if ($net10) {
    Add-Result '.NET Runtime 10' 'OK' $dotnet
} else {
    Add-Result '.NET Runtime 10' 'FAIL' 'not installed: houseCARL cannot start (x64 runtime, not the SDK)' 'winget install Microsoft.DotNet.Runtime.10  (or https://dotnet.microsoft.com/download/dotnet/10.0)'
}

# ---------------------------------------------------------------- MO2 instance and game
$mo2 = Get-SkyrimVar 'SKYRIM_MO2_DIR'
if (-not $mo2) {
    Add-Result 'SKYRIM_MO2_DIR' 'WARN' 'not set: houseCARL will ask for the instance on first use' 'setup.cmd -Mo2Dir "<folder with ModOrganizer.ini>"'
} elseif (-not (Test-Path -LiteralPath $mo2)) {
    Add-Result 'SKYRIM_MO2_DIR' 'FAIL' "does not exist: $mo2" 'setup.cmd -Mo2Dir "<folder with ModOrganizer.ini>"'
} else {
    $ini = Join-Path $mo2 'ModOrganizer.ini'
    if (-not (Test-Path -LiteralPath $ini)) {
        Add-Result 'SKYRIM_MO2_DIR' 'FAIL' "no ModOrganizer.ini in $mo2" 'setup.cmd -Mo2Dir "<folder with ModOrganizer.ini>"'
    } else {
        $gamePath = ''
        try {
            $line = Select-String -LiteralPath $ini -Pattern '^\s*gamePath\s*=\s*(.*)$' -ErrorAction Stop | Select-Object -First 1
            if ($line) { $gamePath = $line.Matches[0].Groups[1].Value.Trim().Trim('"') }
        } catch { }
        # MO2 writes binary ini values as @ByteArray(..\\) - unescape so the path can be judged
        if ($gamePath -match '^@ByteArray\((.*)\)$') { $gamePath = $Matches[1].Replace('\\', '\') }
        $gamePath = $gamePath.Trim()
        $mods = Get-FileCount (Join-Path $mo2 'mods') '*'
        $profiles = Get-FileCount (Join-Path $mo2 'profiles') '*'
        Add-Result 'MO2 instance' 'OK' "$mods mods, $profiles profiles, gamePath='$gamePath'"
        if ($gamePath -match '^\s*\.\.') {
            Add-Result 'MO2 gamePath' 'WARN' 'relative gamePath (portable MO2): the houseCARL release may not resolve it' 'setup.cmd detects this and builds houseCARL from source automatically; if you installed by hand, rerun setup.cmd.'
        }
        if ($gamePath -and -not $gamePath.StartsWith('..')) {
            $resolved = $gamePath
            if (-not [System.IO.Path]::IsPathRooted($resolved)) { $resolved = Join-Path $mo2 $resolved }
            if (Test-Path -LiteralPath $resolved) {
                Add-Result 'game folder' 'OK' $resolved
            } else {
                Add-Result 'game folder' 'WARN' "gamePath points at a missing folder: $resolved" 'Fix the game path in MO2 (GUI), then rerun.'
            }
        }
    }
}

$game = Get-SkyrimVar 'SKYRIM_GAME_DIR'
if (-not $game) {
    Add-Result 'SKYRIM_GAME_DIR' 'WARN' 'not set (optional: the Address Library fallback)' 'setup.cmd sets it when it can detect the game.'
} elseif (Test-Path -LiteralPath (Join-Path $game 'SkyrimSE.exe')) {
    $version = (Get-Item -LiteralPath (Join-Path $game 'SkyrimSE.exe')).VersionInfo.FileVersion
    Add-Result 'SKYRIM_GAME_DIR' 'OK' "$game (SkyrimSE.exe $version)"
} else {
    Add-Result 'SKYRIM_GAME_DIR' 'WARN' "no SkyrimSE.exe in $game" 'set SKYRIM_GAME_DIR to the game folder, or ignore this if MO2 resolves it.'
}

# ---------------------------------------------------------------- RE workspace (optional)
$re = Get-SkyrimVar 'SKYRIM_RE_DIR'
if (-not $re -or -not (Test-Path -LiteralPath $re)) {
    $repoRe = Join-Path $Repo 're'
    if (Test-Path -LiteralPath $repoRe) { $re = $repoRe }
    elseif (-not $re) { $re = Join-Path $home_ 're' }
}
if (-not (Test-Path -LiteralPath $re)) {
    Add-Result 'RE workspace' 'SKIP' "$re (not installed)" 'Only for reverse engineering: setup.cmd -Ghidra'
} else {
    $venv = Join-Path $re 'venv\Scripts\pyghidra-mcp.exe'
    $jdk = @(Get-ChildItem -LiteralPath $re -Directory -Filter 'jdk-*' -ErrorAction SilentlyContinue).Count
    $ghidra = @(Get-ChildItem -LiteralPath $re -Directory -Filter 'ghidra_*_PUBLIC' -ErrorAction SilentlyContinue).Count
    $exe = Join-Path $re 'bins\skyrim\SkyrimSE.exe'
    if ((Test-Path -LiteralPath $venv) -and $jdk -gt 0 -and $ghidra -gt 0) {
        Add-Result 'RE workspace' 'OK' "$re (venv, JDK, Ghidra)"
        if (Test-Path -LiteralPath $exe) { Add-Result 'SkyrimSE.exe copy' 'OK' $exe } else { Add-Result 'SkyrimSE.exe copy' 'WARN' "missing: $exe" 'setup.cmd -Ghidra copies it for analysis.' }
        $gdt = Join-Path $re 'gdt\CommonLibSSE_SE_b93280e.gdt'
        if (Test-Path -LiteralPath $gdt) { Add-Result 'Skyrim RE Toolkit (GDT)' 'OK' $gdt }
        $bgs = Join-Path $re 'BethesdaGhidraScripts\run.py'
        if (Test-Path -LiteralPath $bgs) { Add-Result 'BethesdaGhidraScripts' 'OK' (Split-Path -Parent $bgs) }
    } else {
        Add-Result 'RE workspace' 'WARN' "incomplete in $re (venv=$([bool](Test-Path -LiteralPath $venv)), jdk=$jdk, ghidra=$ghidra)" 'setup.cmd -Ghidra'
    }
}

# ---------------------------------------------------------------- Papyrus compiler
$papyrusCandidates = @()
if ($env:PAPYRUS_COMPILER_DIR) { $papyrusCandidates += (Join-Path $env:PAPYRUS_COMPILER_DIR 'papyrus-compiler\papyrus.exe'), (Join-Path $env:PAPYRUS_COMPILER_DIR 'papyrus.exe') }
$papyrusCandidates += (Join-Path $home_ 'papyrus-compiler\papyrus-compiler\papyrus.exe'), (Join-Path $Repo 'tools\papyrus-compiler\papyrus-compiler\papyrus.exe')
if ($game) { $papyrusCandidates += (Join-Path $game 'Papyrus Compiler\PapyrusCompiler.exe') }
$papyrusExe = $papyrusCandidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
if ($papyrusExe) { Add-Result 'Papyrus compiler' 'OK' $papyrusExe }
else { Add-Result 'Papyrus compiler' 'WARN' 'none (open-source papyrus-compiler or the Creation Kit PapyrusCompiler.exe)' 'setup.cmd installs papyrus-compiler; scripts\papyrus\papyrusc.py which' }

# ---------------------------------------------------------------- SkyLink AI (optional, live game bridge)
$skylinkExe = if ($env:SKYLINK_EXE) { $env:SKYLINK_EXE } else { Join-Path $home_ 'skylink\server\SkyrimMCP.exe' }
if (Test-Path -LiteralPath $skylinkExe) {
    $skylinkMod = $null
    if ($mo2 -and (Test-Path -LiteralPath (Join-Path $mo2 'mods'))) {
        $skylinkMod = Get-ChildItem -LiteralPath (Join-Path $mo2 'mods') -Directory -ErrorAction SilentlyContinue |
                      Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'SKSE\Plugins\SkyrimMCPPlugin.dll') } | Select-Object -First 1
    }
    if ($skylinkMod) { Add-Result 'SkyLink AI' 'OK' "server $skylinkExe; SKSE plugin in mod '$($skylinkMod.Name)' (enable it in MO2)" }
    else { Add-Result 'SkyLink AI' 'WARN' "server $skylinkExe, but no MO2 mod carries SKSE\Plugins\SkyrimMCPPlugin.dll" 'setup.cmd -SkyLink creates the mod "SkyLink AI"; then enable it in MO2.' }
} else {
    Add-Result 'SkyLink AI' 'SKIP' 'not installed (optional: live game bridge)' 'setup.cmd -SkyLink'
}

# ---------------------------------------------------------------- Havok and Behavior tools
$sage = Join-Path $Repo 'tools\SageHavokEditor\SageHavokEditor.exe'
if (Test-Path -LiteralPath $sage) {
    Add-Result 'SageHavokEditor' 'OK' $sage
}

# ---------------------------------------------------------------- python
$python = $null
foreach ($name in @('python', 'python3', 'py')) {
    $c = Get-Command $name -ErrorAction SilentlyContinue
    if ($c) { $python = $c.Source; break }
}
if ($python) {
    try { $pyVersion = (& $python --version 2>&1) -join ' ' } catch { $pyVersion = 'unknown version' }
    Add-Result 'python' 'OK' "$pyVersion ($python)"
} else {
    Add-Result 'python' 'WARN' 'no python on PATH: the scripts/ utilities need Python 3' 'winget install Python.Python.3.13 (or setup.cmd -Ghidra, which brings its own venv)'
}

# ---------------------------------------------------------------- MCP launchers, skills, data
foreach ($launcher in @('scripts\run_housecarl.cmd', 'scripts\re\run_ghidra_mcp.cmd', 'scripts\run_sage_havok.cmd')) {
    $path = Join-Path $Repo $launcher
    if (Test-Path -LiteralPath $path) { Add-Result $launcher 'OK' $path } else { Add-Result $launcher 'FAIL' "missing: $path" 'git pull (the launchers are part of the repo).' }
}

$dataFile = Join-Path $Repo 'data\se_id_names.tsv'
if (Test-Path -LiteralPath $dataFile) {
    Add-Result 'data\se_id_names.tsv' 'OK' "$(Get-FileCount (Split-Path -Parent $dataFile) 'se_id_names.tsv') file, $(@(Get-Content -LiteralPath $dataFile).Count) rows"
} else {
    Add-Result 'data\se_id_names.tsv' 'WARN' 'missing: REL::ID names are unavailable' 'git pull (or scripts\re\build_id_names.py on the author machine).'
}

$skillDir = Join-Path $Repo 'skills'
$skills = @(Get-ChildItem -LiteralPath $skillDir -Directory -ErrorAction SilentlyContinue | Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'SKILL.md') })
$badNames = @()
$undocumented = @()
$index = Join-Path $skillDir 'README.md'
$indexText = ''
if (Test-Path -LiteralPath $index) { $indexText = Get-Content -LiteralPath $index -Raw }
foreach ($skill in $skills) {
    $head = @(Get-Content -LiteralPath (Join-Path $skill.FullName 'SKILL.md') -TotalCount 15)
    $nameLine = $head | Where-Object { $_ -match '^name:\s*(\S+)\s*$' } | Select-Object -First 1
    if (-not $nameLine) { $badNames += "$($skill.Name) (no name: in frontmatter)" ; continue }
    $declared = [regex]::Match($nameLine, '^name:\s*(\S+)\s*$').Groups[1].Value
    if ($declared -ne $skill.Name) { $badNames += "$($skill.Name) declares '$declared'" }
    if ($indexText -and $indexText -notmatch [regex]::Escape("($($skill.Name)/SKILL.md)")) { $undocumented += $skill.Name }
}
if ($skills.Count -eq 0) {
    Add-Result 'skills' 'FAIL' "none found under $skillDir" 'git pull.'
} elseif ($badNames.Count -eq 0) {
    Add-Result 'skills' 'OK' "$($skills.Count) skills, frontmatter names match their folders"
} else {
    Add-Result 'skills' 'WARN' ("frontmatter/folder mismatch: " + ($badNames -join '; ')) 'Fix the name: line in SKILL.md (see CONTRIBUTING.md).'
}
if ($undocumented.Count -gt 0) {
    Add-Result 'skills index' 'WARN' ("not listed in skills/README.md: " + ($undocumented -join ', ')) 'Add a row to skills/README.md.'
} elseif ($skills.Count -gt 0) {
    Add-Result 'skills index' 'OK' 'every skill is listed in skills/README.md'
}

$claudeSkills = Join-Path $env:USERPROFILE '.claude\skills\housecarl'
if (Test-Path -LiteralPath $claudeSkills) {
    Add-Result 'duplicate skills' 'WARN' "houseCARL's own installer put skills in ${claudeSkills}: they will be doubled" 'houseCARL-Setup.exe --uninstall --claude'
} else {
    Add-Result 'duplicate skills' 'OK' 'no second copy in ~\.claude\skills\housecarl'
}

# ---------------------------------------------------------------- summary
$fails = @($results | Where-Object { $_.status -eq 'FAIL' })
$warns = @($results | Where-Object { $_.status -eq 'WARN' })

if ($Json) {
    [pscustomobject]@{ repo = $Repo; ok = ($fails.Count -eq 0); checks = $results; fixes = $fixes } | ConvertTo-Json -Depth 5
} else {
    Write-Host ''
    if ($fails.Count -eq 0) {
        Write-Host "  ready: $($results.Count - $warns.Count - @($results | Where-Object { $_.status -eq 'SKIP' }).Count) ok, $($warns.Count) warnings" -ForegroundColor Green
    } else {
        Write-Host "  $($fails.Count) failure(s), $($warns.Count) warning(s)" -ForegroundColor Red
    }
    if ($Fix -and $fixes.Count -gt 0) {
        Write-Host ''
        Write-Host '  repair:' -ForegroundColor Cyan
        $n = 0
        foreach ($f in $fixes) { $n++; Write-Host ("   $n. $f") }
    } elseif ($fixes.Count -gt 0) {
        Write-Host '  rerun with -Fix to see the repair commands.' -ForegroundColor DarkGray
    }
    Write-Host ''
}

if ($fails.Count -gt 0) { exit 1 }
