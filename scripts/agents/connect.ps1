<#
.SYNOPSIS
    Print the MCP server configuration of this machine for any agent client, and optionally link the skills.

.DESCRIPTION
    SkyrimTools ships two stdio MCP servers behind .cmd launchers: housecarl (live MO2 load order) and pyghidra-mcp
    (headless Ghidra). .mcp.json in the repo root is the Claude Code form and uses ${CLAUDE_PLUGIN_ROOT}, which no other
    client understands. This script prints the same two servers in the shape a given client expects, with this repo's
    absolute paths, plus the file it belongs in.

    -LinkSkills instead creates one directory junction per skill in an agent's skills folder, so an edit here is live
    there. Real directories are never overwritten; -Force only replaces an existing junction.

    See docs/mcp-clients.md for the per-client prose and pitfalls.

.PARAMETER Client
    claude, codex, vscode, cursor, windsurf, cline, gemini, opencode, or json (client-neutral mcpServers block).

.PARAMETER Portable
    Use %SKYRIM_TOOLS_REPO% instead of the absolute repo path (works only when the client starts the command through
    cmd.exe and the variable is set).

.PARAMETER LinkSkills
    Create the skill junctions instead of printing a config.

.PARAMETER SkillsTarget
    Folder that receives the junctions. Defaults to ~\.claude\skills for -Client claude and ~\.codex\skills for codex;
    required for any other client.

.PARAMETER Force
    Replace an existing junction. Never removes a real directory.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\agents\connect.ps1 -Client codex

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\agents\connect.ps1 -Client claude -LinkSkills
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [ValidateSet('claude', 'codex', 'vscode', 'cursor', 'windsurf', 'cline', 'gemini', 'opencode', 'json')]
    [string]$Client = 'json',
    [switch]$Portable,
    [switch]$LinkSkills,
    [string]$SkillsTarget,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$Repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

$housecarl = Join-Path $Repo 'scripts\run_housecarl.cmd'
$ghidra = Join-Path $Repo 'scripts\re\run_ghidra_mcp.cmd'
foreach ($launcher in @($housecarl, $ghidra)) {
    if (-not (Test-Path -LiteralPath $launcher)) { throw "launcher missing: $launcher (incomplete checkout?)" }
}
if ($Portable) {
    $housecarl = '%SKYRIM_TOOLS_REPO%\scripts\run_housecarl.cmd'
    $ghidra = '%SKYRIM_TOOLS_REPO%\scripts\re\run_ghidra_mcp.cmd'
}

$configPaths = @{
    claude   = 'already wired by setup.cmd: <repo>\.mcp.json + plugin registration (~\.claude\settings.json); /mcp in session'
    codex    = "$env:USERPROFILE\.codex\config.toml  (append the tables)"
    vscode   = '<repo>\.vscode\mcp.json  (this repo already has it; elsewhere copy the block)'
    cursor   = "$env:USERPROFILE\.cursor\mcp.json  (or .cursor\mcp.json inside a project)"
    windsurf = "$env:USERPROFILE\.codeium\windsurf\mcp_config.json"
    cline    = 'MCP Servers -> Configure MCP Servers (writes cline_mcp_settings.json), or edit that file'
    gemini   = "$env:USERPROFILE\.gemini\settings.json"
    opencode = 'opencode.json (project) or ~\.config\opencode\opencode.json'
    json     = 'any client: mcpServers shape, adapt the keys'
}

function New-StdioServer {
    param([string]$Path, [switch]$WithType)
    if ($WithType) {
        return [pscustomobject]@{ type = 'stdio'; command = 'cmd.exe'; args = @('/c', $Path) }
    }
    return [pscustomobject]@{ command = 'cmd.exe'; args = @('/c', $Path) }
}

function Write-Section {
    param([string]$Title)
    Write-Host ''
    Write-Host $Title -ForegroundColor Cyan
    Write-Host ('-' * $Title.Length) -ForegroundColor DarkGray
}

function Show-Json {
    param($Object)
    Write-Host ($Object | ConvertTo-Json -Depth 8)
}

# ---------------------------------------------------------------- skills junctions
if ($LinkSkills) {
    $target = $SkillsTarget
    if (-not $target) {
        $target = switch ($Client) {
            'claude' { Join-Path $env:USERPROFILE '.claude\skills' }
            'codex' { Join-Path $env:USERPROFILE '.codex\skills' }
            default { '' }
        }
    }
    if (-not $target) {
        Write-Host "  -LinkSkills needs -SkillsTarget for '$Client': only claude (~\.claude\skills) and codex (~\.codex\skills) have a known skills folder here." -ForegroundColor Red
        exit 1
    }
    if (-not (Test-Path -LiteralPath $target)) {
        if ($PSCmdlet.ShouldProcess($target, 'create directory')) { New-Item -ItemType Directory -Path $target -Force | Out-Null }
    }
    Write-Section "Skills -> $target"
    $skills = @(Get-ChildItem -LiteralPath (Join-Path $Repo 'skills') -Directory | Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'SKILL.md') })
    if ($skills.Count -eq 0) { Write-Host '  no skills found in the repo' -ForegroundColor Red; exit 1 }
    $linked = 0; $skipped = 0; $failed = 0
    foreach ($skill in $skills) {
        $link = Join-Path $target $skill.Name
        $exists = Test-Path -LiteralPath $link
        $isLink = $false
        $pointsHere = $false
        if ($exists) {
            $item = Get-Item -LiteralPath $link -Force
            $isLink = [bool]($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint)
            if ($isLink) {
                $resolved = $null
                try { $resolved = @($item.Target)[0] } catch { }
                if ($resolved) {
                    $pointsHere = ((Resolve-Path -LiteralPath $resolved -ErrorAction SilentlyContinue).Path -eq (Resolve-Path -LiteralPath $skill.FullName).Path)
                }
            }
        }
        if ($exists -and $pointsHere) {
            Write-Host "  linked   $($skill.Name) (already)" -ForegroundColor DarkGray
            $linked++
            continue
        }
        if ($exists -and -not $isLink) {
            Write-Host "  skipped  $($skill.Name): a real directory is there, not a link - left untouched" -ForegroundColor Yellow
            $skipped++
            continue
        }
        if ($exists -and $isLink -and -not $Force) {
            Write-Host "  skipped  $($skill.Name): another link is there (use -Force to replace)" -ForegroundColor Yellow
            $skipped++
            continue
        }
        try {
            if ($exists -and $isLink) {
                if ($PSCmdlet.ShouldProcess($link, 'remove old junction')) { [System.IO.Directory]::Delete($link, $false) }
            }
            if ($PSCmdlet.ShouldProcess($link, "junction -> $($skill.FullName)")) {
                New-Item -ItemType Junction -Path $link -Target $skill.FullName | Out-Null
            }
            Write-Host $(if ($WhatIfPreference) { "  would link $($skill.Name)" } else { "  linked   $($skill.Name)" }) -ForegroundColor Green
            $linked++
        } catch {
            Write-Host "  failed   $($skill.Name): $($_.Exception.Message)" -ForegroundColor Red
            $failed++
        }
    }
    Write-Host ''
    Write-Host "  $linked linked, $skipped skipped, $failed failed" -ForegroundColor $(if ($failed) { 'Red' } else { 'Green' })
    Write-Host '  The junction points into this repo: git pull updates the other agent too.' -ForegroundColor DarkGray
    if ($failed) { exit 1 }
    exit 0
}

# ---------------------------------------------------------------- MCP config
$hc = New-StdioServer $housecarl -WithType
$gh = New-StdioServer $ghidra -WithType

Write-Section "MCP servers for $Client"
Write-Host ('  config: ' + $configPaths[$Client]) -ForegroundColor DarkGray
Write-Host '  launchers read the SKYRIM_* user variables themselves; no env block is needed.'
Write-Host '  startup: houseCARL a few seconds, pyghidra-mcp 20-60 s (JVM) - raise the client timeout if it gives up.'

switch ($Client) {
    'codex' {
        $hcPath = $housecarl
        $ghPath = $ghidra
        Write-Host ''
        Write-Host @"
[mcp_servers.housecarl]
command = "cmd.exe"
args = ["/c", '$hcPath']
startup_timeout_sec = 120

[mcp_servers.pyghidra-mcp]
command = "cmd.exe"
args = ["/c", '$ghPath']
startup_timeout_sec = 300
"@
    }
    'opencode' {
        Show-Json ([pscustomobject]@{
                mcp = [pscustomobject]@{
                    housecarl    = [pscustomobject]@{ type = 'local'; command = @('cmd.exe', '/c', $housecarl); enabled = $true }
                    'pyghidra-mcp' = [pscustomobject]@{ type = 'local'; command = @('cmd.exe', '/c', $ghidra); enabled = $true }
                }
            })
    }
    'vscode' {
        Show-Json ([pscustomobject]@{ servers = [pscustomobject]@{ housecarl = $hc; 'pyghidra-mcp' = $gh } })
    }
    { $_ -in @('cursor', 'windsurf', 'cline', 'gemini', 'json') } {
        $plainHc = New-StdioServer $housecarl
        $plainGh = New-StdioServer $ghidra
        Show-Json ([pscustomobject]@{ mcpServers = [pscustomobject]@{ housecarl = $plainHc; 'pyghidra-mcp' = $plainGh } })
    }
    'claude' {
        Show-Json ([pscustomobject]@{ mcpServers = [pscustomobject]@{ housecarl = $hc; 'pyghidra-mcp' = $gh } })
        Write-Host ''
        Write-Host '  Normally nothing to paste: setup.cmd registered the plugin. By hand:' -ForegroundColor DarkGray
        Write-Host ('  claude mcp add --transport stdio housecarl -- cmd.exe /c "' + $housecarl + '"')
    }
}

if ($Portable) {
    Write-Host ''
    Write-Host '  portable form: %SKYRIM_TOOLS_REPO% is expanded by cmd.exe at launch, so the file works after a move - as long' -ForegroundColor DarkGray
    Write-Host '  as the client starts the command through cmd.exe and the variable is visible to it.' -ForegroundColor DarkGray
}

# ---------------------------------------------------------------- readiness
$home_ = [Environment]::GetEnvironmentVariable('SKYRIM_TOOLS_HOME', 'User')
if (-not $home_) { $home_ = Join-Path $env:LOCALAPPDATA 'SkyrimTools' }
$hcExe = [Environment]::GetEnvironmentVariable('HOUSECARL_EXE', 'User')
if (-not $hcExe) { $hcExe = Join-Path $home_ 'housecarl\server\housecarl-mcp.exe' }
$re = [Environment]::GetEnvironmentVariable('SKYRIM_RE_DIR', 'User')
if (-not $re) { $re = Join-Path $home_ 're' }

Write-Section 'Readiness'
if (Test-Path -LiteralPath $hcExe) {
    Write-Host "  housecarl     ready: $hcExe" -ForegroundColor Green
} else {
    Write-Host "  housecarl     NOT installed ($hcExe) - run setup.cmd, then restart the client" -ForegroundColor Red
}
if (Test-Path -LiteralPath (Join-Path $re 'venv\Scripts\pyghidra-mcp.exe')) {
    Write-Host "  pyghidra-mcp  ready: $re" -ForegroundColor Green
} else {
    Write-Host "  pyghidra-mcp  not installed ($re) - optional, setup.cmd -Ghidra" -ForegroundColor Yellow
}
$repoVar = [Environment]::GetEnvironmentVariable('SKYRIM_TOOLS_REPO', 'User')
if (-not $repoVar) {
    Write-Host '  SKYRIM_TOOLS_REPO is not set: the skills will not find scripts/ - run setup.cmd' -ForegroundColor Yellow
} elseif ($repoVar.TrimEnd('\') -ne $Repo.TrimEnd('\')) {
    Write-Host "  note: SKYRIM_TOOLS_REPO points at $repoVar, this copy is $Repo" -ForegroundColor Yellow
}
Write-Host ''
Write-Host '  Full check of the machine: scripts\agents\doctor.ps1 -Fix' -ForegroundColor DarkGray
Write-Host ''
