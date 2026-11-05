<#
.SYNOPSIS
    Установщик SkyrimTools: плагин Claude Code со скиллами и MCP-серверами для моддинга Skyrim SE.

.DESCRIPTION
    Что делает, по шагам (перед началом показывает план и ждёт Enter):
      1. .NET Runtime 10 (x64) — нужен houseCARL; ставится через winget, если его нет.
      2. houseCARL — MCP-сервер для load order / записей / Papyrus / Nexus. Скачивается релиз с GitHub
         (SHA-256 сверяется), в папку установки кладётся только сервер (скиллы уже есть в этом репо).
      3. По желанию (-Ghidra): рабочая папка для реверса — JDK 25, Ghidra 12.2, Python venv с pyghidra-mcp,
         копия SkyrimSE.exe для анализа. Около 2 ГБ на диске.
      4. Пользовательские переменные окружения SKYRIM_* (их читают лаунчеры, скрипты и скиллы).
      5. Регистрация плагина в %USERPROFILE%\.claude\settings.json (до правки делается .bak).
    Повторный запуск безопасен: уже установленное пропускается, это же и обновление.

.PARAMETER Mo2Dir
    Папка экземпляра Mod Organizer 2, та, где лежит ModOrganizer.ini. Без параметра скрипт спросит.

.PARAMETER Ghidra
    Поставить набор для реверса (Ghidra + JDK + pyghidra-mcp). -NoGhidra — не ставить и не спрашивать.

.PARAMETER InstallDir
    Куда ставить тяжёлые части. По умолчанию %LOCALAPPDATA%\SkyrimTools. Если указан явно, ранее
    заданные свои пути (HOUSECARL_EXE, SKYRIM_RE_DIR) игнорируются и всё ставится сюда.

.PARAMETER HousecarlVersion
    Тег релиза houseCARL (по умолчанию проверенный v2.1.2) или latest.

.PARAMETER HousecarlFromSource
    Собрать houseCARL из исходников того же тега с фиксом относительного gamePath (нужен .NET SDK 10, ставится
    через winget). Включается сам, если в ModOrganizer.ini относительный gamePath (портативные сборки, gamePath=..\).

.PARAMETER Yes
    Не задавать вопросов: брать значения по умолчанию и не ждать подтверждения.

.PARAMETER FilesOnly
    Только скачать и разложить файлы: не трогать переменные окружения и settings.json (для проверки).

.PARAMETER Uninstall
    Убрать регистрацию плагина и переменные SKYRIM_*; папку установки удалить после вопроса.

.EXAMPLE
    .\setup.cmd
    .\setup.cmd -Mo2Dir "D:\Games\MyList\MO2" -Ghidra
    .\setup.cmd -Uninstall
#>
[CmdletBinding()]
param(
    [string]$Mo2Dir,
    [switch]$Ghidra,
    [switch]$NoGhidra,
    [string]$InstallDir,
    [string]$HousecarlVersion = 'v2.1.2',
    [switch]$HousecarlFromSource,
    [switch]$Yes,
    [switch]$FilesOnly,
    [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

$Repo = $PSScriptRoot
$MarketplaceName = 'skyrim-tools'
$PluginId = 'skyrim-tools@skyrim-tools'
$ClaudeDir = Join-Path $env:USERPROFILE '.claude'
$SettingsPath = Join-Path $ClaudeDir 'settings.json'
$EnvNames = 'SKYRIM_TOOLS_REPO', 'SKYRIM_TOOLS_HOME', 'SKYRIM_MO2_DIR', 'SKYRIM_GAME_DIR', 'SKYRIM_RE_DIR'

# Проверенные версии: Ghidra 12.2 требует Java 25; pyghidra-mcp 0.3.0 проверен с ней.
$Pins = @{
    GhidraUrl = 'https://github.com/NationalSecurityAgency/ghidra/releases/download/Ghidra_12.2_build/ghidra_12.2_PUBLIC_20261016.zip'
    GhidraSha = '2c2cd776db3c1f6a097ba418922378ac3649cadd5e844a6f5f088ae628a7be67'
    JdkUrl    = 'https://github.com/adoptium/temurin25-binaries/releases/download/jdk-25.0.5%2B8/OpenJDK25U-jdk_x64_windows_hotspot_25.0.5_8.zip'
    JdkSha    = '636bdc13dc649ddc7d5921c5c7d23cca6e44fd19d662b45cc9c02135a6c96c42'
}

# ---------------------------------------------------------------- вывод и вопросы

function Say([string]$Text) { Write-Host $Text }
function Step([string]$Text) { Write-Host ''; Write-Host "== $Text" -ForegroundColor Cyan }
function Ok([string]$Text) { Write-Host "   OK  $Text" -ForegroundColor Green }
function Warn([string]$Text) { Write-Host "   !!  $Text" -ForegroundColor Yellow; $script:Warnings += $Text }
function Fail([string]$Text) { Write-Host ''; Write-Host "ОШИБКА: $Text" -ForegroundColor Red; exit 1 }
$script:Warnings = @()

function Ask([string]$Question, [string]$Default) {
    if ($Yes) { return $Default }
    $hint = if ($Default) { " [$Default]" } else { '' }
    $answer = Read-Host "$Question$hint"
    if ([string]::IsNullOrWhiteSpace($answer)) { return $Default }
    return $answer.Trim().Trim('"').Trim("'")
}

function AskYesNo([string]$Question, [bool]$Default) {
    if ($Yes) { return $Default }
    $hint = if ($Default) { '[Д/н]' } else { '[д/Н]' }
    while ($true) {
        $answer = (Read-Host "$Question $hint").Trim().ToLower()
        if ($answer -eq '') { return $Default }
        if ($answer -in 'y', 'yes', 'д', 'да') { return $true }
        if ($answer -in 'n', 'no', 'н', 'нет') { return $false }
    }
}

# Внешние программы: в PowerShell 5.1 вывод в stderr при ErrorActionPreference=Stop превращается в исключение.
function Invoke-Native([scriptblock]$Block) {
    $old = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & $Block } finally { $ErrorActionPreference = $old }
}

function Get-UserEnv([string]$Name) { [Environment]::GetEnvironmentVariable($Name, 'User') }

function Set-UserEnv([string]$Name, [string]$Value) {
    if ((Get-UserEnv $Name) -ne $Value) { [Environment]::SetEnvironmentVariable($Name, $Value, 'User') }
    Set-Item "env:$Name" $Value
}

# ---------------------------------------------------------------- загрузка

$script:Temp = $null
function Get-TempDir {
    if (-not $script:Temp) {
        $script:Temp = Join-Path $env:TEMP ('skyrimtools-setup-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
        New-Item -ItemType Directory -Force $script:Temp | Out-Null
    }
    $script:Temp
}

function Get-File([string]$Url, [string]$Sha256, [string]$What, [switch]$NoHash) {
    $dir = Join-Path (Get-TempDir) ([guid]::NewGuid().ToString('N').Substring(0, 8))
    New-Item -ItemType Directory -Force $dir | Out-Null
    $file = Join-Path $dir ([Uri]::UnescapeDataString(($Url -split '/')[-1]))
    Say "   скачиваю $What ..."
    Invoke-Native { & curl.exe -L --fail --retry 3 --silent --show-error -o $file $Url }
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $file)) { Fail "не удалось скачать $Url" }
    if ($Sha256) {
        $got = (Get-FileHash -Algorithm SHA256 -LiteralPath $file).Hash.ToLower()
        if ($got -ne $Sha256.ToLower()) {
            Remove-Item -LiteralPath $file -Force
            Fail "контрольная сумма $What не совпала (ожидалось $Sha256, получено $got). Файл удалён."
        }
        Ok "$What скачан, SHA-256 совпал"
    }
    elseif ($NoHash) { Ok "$What скачан" }
    else { Warn "у $What нет опубликованной контрольной суммы, проверить нечем" }
    $file
}

function Expand-Zip([string]$Zip, [string]$Dest) {
    New-Item -ItemType Directory -Force $Dest | Out-Null
    Invoke-Native { & tar.exe -xf $Zip -C $Dest }
    if ($LASTEXITCODE -ne 0) { Fail "не удалось распаковать $Zip" }
}

# ---------------------------------------------------------------- поиск MO2 и игры

function Read-Mo2Value([string]$Mo2, [string]$Key) {
    $ini = Join-Path $Mo2 'ModOrganizer.ini'
    $line = Get-Content -LiteralPath $ini -Encoding UTF8 | Where-Object { $_ -match "^$Key\s*=" } | Select-Object -First 1
    if (-not $line) { return $null }
    $value = ($line -replace "^$Key\s*=\s*", '').Trim()
    if ($value -match '^@ByteArray\((.*)\)$') { $value = $Matches[1] }
    $value = $value.Replace('\\', '\').Trim('"')
    if ($value) { $value } else { $null }
}

# Портативные сборки пишут gamePath=..\ — houseCARL до v2.1.2 включительно такой путь не понимает.
function Test-Mo2Relative([string]$Mo2) {
    foreach ($key in 'gamePath', 'base_directory') {
        $v = Read-Mo2Value $Mo2 $key
        if ($v -and -not [IO.Path]::IsPathRooted($v)) { return $true }
    }
    $false
}

function Read-GamePath([string]$Mo2) {
    $value = Read-Mo2Value $Mo2 'gamePath'
    if (-not $value) { return $null }
    if (-not [IO.Path]::IsPathRooted($value)) { $value = Join-Path $Mo2 $value }
    try { (Resolve-Path -LiteralPath $value).Path } catch { $null }
}

function Find-GameDir([string]$Mo2) {
    $candidates = @()
    if ($Mo2) { $candidates += Read-GamePath $Mo2 }
    foreach ($key in 'HKLM:\SOFTWARE\WOW6432Node\Bethesda Softworks\Skyrim Special Edition',
                     'HKLM:\SOFTWARE\Bethesda Softworks\Skyrim Special Edition') {
        try { $candidates += (Get-ItemProperty -LiteralPath $key -Name 'installed path').'installed path' } catch { }
    }
    foreach ($c in $candidates) {
        if ($c -and (Test-Path -LiteralPath (Join-Path $c 'SkyrimSE.exe'))) { return $c.TrimEnd('\') }
    }
    $null
}

# ---------------------------------------------------------------- .NET и Python

function Test-DotNet10 {
    foreach ($root in "$env:ProgramFiles\dotnet", "$env:USERPROFILE\.dotnet") {
        $shared = Join-Path $root 'shared\Microsoft.NETCore.App'
        if ((Test-Path -LiteralPath $shared) -and (Get-ChildItem -LiteralPath $shared -Directory -Filter '10.*' -ErrorAction SilentlyContinue)) { return $true }
    }
    $false
}

function Get-Dotnet {
    $exe = Join-Path $env:ProgramFiles 'dotnet\dotnet.exe'
    if (Test-Path -LiteralPath $exe) { return $exe }
    $cmd = Get-Command dotnet.exe -ErrorAction SilentlyContinue
    if ($cmd) { $cmd.Source } else { $null }
}

# houseCARL собирается SDK 10.0.400+ (его global.json).
function Test-DotNetSdk10 {
    $dotnet = Get-Dotnet
    if (-not $dotnet) { return $false }
    $sdks = Invoke-Native { & $dotnet --list-sdks 2>$null }
    foreach ($s in @($sdks)) { if ("$s" -match '^10\.0\.(\d+)' -and [int]$Matches[1] -ge 400) { return $true } }
    $false
}

# Сборка houseCARL из исходников тега + фикс относительного gamePath (тот же порядок, что в их scripts\build-plugin.ps1:
# генератор corpus.json, publish сервера, corpus рядом с exe). Возвращает корень исходников; сервер в out\server.
function Build-HousecarlFromSource([string]$Tag) {
    if (-not (Test-DotNetSdk10)) {
        if (Test-Winget) {
            Say '   нужен .NET SDK 10 для сборки, ставлю через winget ...'
            Invoke-Native { & winget.exe install --id Microsoft.DotNet.SDK.10 -e --architecture x64 --accept-package-agreements --accept-source-agreements --silent }
        }
        if (-not (Test-DotNetSdk10)) { Fail '.NET SDK 10.0.400+ не установлен: https://dotnet.microsoft.com/download/dotnet/10.0 (SDK, x64)' }
    }
    $dotnet = Get-Dotnet
    try { $commit = (Invoke-RestMethod -Uri "https://api.github.com/repos/Avick3110/houseCARL/commits/$Tag" -Headers @{ 'User-Agent' = 'SkyrimTools-setup' }).sha }
    catch { Fail "не получилось узнать коммит тега houseCARL $Tag : $($_.Exception.Message)" }
    $zip = Get-File "https://github.com/Avick3110/houseCARL/archive/$commit.zip" $null "исходники houseCARL $Tag (коммит $($commit.Substring(0, 8)))" -NoHash
    $unpacked = Join-Path (Split-Path $zip) 'src'
    Expand-Zip $zip $unpacked
    $root = (Get-ChildItem -LiteralPath $unpacked -Directory | Select-Object -First 1).FullName

    $file = Join-Path $root 'src\housecarl-core\Mo2Instance.cs'
    $text = [IO.File]::ReadAllText($file)
    $gameLine = 'var gamePath = CleanValue(FindValue(lines, "gamePath"));'
    $baseLine = 'var baseDir  = CleanValue(FindValue(lines, "base_directory"));'
    if ($text.Contains('Anchored(')) { Ok 'фикс относительного gamePath уже есть в исходниках' }
    elseif ($text.Contains($gameLine) -and $text.Contains($baseLine)) {
        $text = $text.Replace($gameLine, 'var gamePath = Anchored(instanceDir, CleanValue(FindValue(lines, "gamePath")));')
        $text = $text.Replace($baseLine, 'var baseDir  = Anchored(instanceDir, CleanValue(FindValue(lines, "base_directory")));')
        $end = $text.LastIndexOf('}')
        $method = "`n    // SkyrimTools setup: MO2 resolves a relative gamePath / base_directory (portable lists: ..\) against the instance folder.`n" +
                  "    static string? Anchored(string instanceDir, string? path)`n" +
                  "        => string.IsNullOrWhiteSpace(path) ? path : Path.GetFullPath(Path.Combine(instanceDir, path));`n"
        $text = $text.Substring(0, $end) + $method + $text.Substring($end)
        [IO.File]::WriteAllText($file, $text, (New-Object Text.UTF8Encoding $false))
        Ok 'фикс относительного gamePath наложен'
    }
    else { Warn 'исходники houseCARL изменились, фикс gamePath не наложен — собираю как есть' }

    $env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'; $env:DOTNET_NOLOGO = '1'
    $log = Join-Path (Split-Path $zip) 'build.log'
    $out = Join-Path $root 'out\server'
    $version = $Tag.TrimStart('v')
    Push-Location -LiteralPath $root
    try {
        Say '   собираю houseCARL (генератор схем + сервер, около минуты) ...'
        Invoke-Native { & $dotnet run --project 'src\housecarl-generator' -c Release -- (Join-Path $root 'generated') (Join-Path $root '_ref') > $log 2>&1 }
        if ($LASTEXITCODE -ne 0) { Get-Content -LiteralPath $log -Tail 30 | ForEach-Object { Say "      $_" }; Fail "генератор houseCARL упал, лог: $log" }
        Invoke-Native { & $dotnet publish 'src\housecarl-mcp' -c Release -r win-x64 --self-contained false "-p:Version=$version" -o $out >> $log 2>&1 }
        if ($LASTEXITCODE -ne 0) { Get-Content -LiteralPath $log -Tail 30 | ForEach-Object { Say "      $_" }; Fail "сборка houseCARL упала, лог: $log" }
    }
    finally { Pop-Location }
    Get-ChildItem -LiteralPath $out -Filter 'appsettings*.json' | Remove-Item -Force
    Copy-Item -LiteralPath (Join-Path $root 'generated\corpus.json') -Destination $out -Force
    if (-not (Test-Path -LiteralPath (Join-Path $out 'housecarl-mcp.exe'))) { Fail 'после сборки нет housecarl-mcp.exe' }
    Ok "houseCARL $Tag собран из исходников"
    $root
}

function Test-Winget { [bool](Get-Command winget.exe -ErrorAction SilentlyContinue) }

function Find-Python {
    $candidates = @(
        @{ Exe = 'py'; Args = @('-3.13') }, @{ Exe = 'py'; Args = @('-3.12') }, @{ Exe = 'py'; Args = @('-3.11') },
        @{ Exe = "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe"; Args = @() },
        @{ Exe = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"; Args = @() },
        @{ Exe = 'python'; Args = @() }, @{ Exe = 'python3'; Args = @() }
    )
    foreach ($c in $candidates) {
        if (-not (Get-Command $c.Exe -ErrorAction SilentlyContinue)) { continue }
        $exe = $c.Exe; $a = $c.Args
        $v = Invoke-Native { & $exe @a -c "import sys;print('%d.%d' % sys.version_info[:2])" 2>$null }
        # 3.10-3.13: под 3.14 у части зависимостей pyghidra-mcp (onnxruntime, chromadb) может не быть сборок.
        if ($LASTEXITCODE -eq 0 -and "$v" -match '^3\.(\d+)$' -and [int]$Matches[1] -ge 10 -and [int]$Matches[1] -le 13) {
            return @{ Exe = $exe; Args = $a; Version = "$v" }
        }
    }
    $null
}

# ---------------------------------------------------------------- settings.json

function Read-Settings {
    if (-not (Test-Path -LiteralPath $SettingsPath)) { return [pscustomobject]@{} }
    $raw = [IO.File]::ReadAllText($SettingsPath)
    if ([string]::IsNullOrWhiteSpace($raw)) { return [pscustomobject]@{} }
    try { $raw | ConvertFrom-Json } catch { $null }
}

function Write-Settings($Settings) {
    New-Item -ItemType Directory -Force $ClaudeDir | Out-Null
    if (Test-Path -LiteralPath $SettingsPath) { Copy-Item -LiteralPath $SettingsPath -Destination "$SettingsPath.skyrimtools.bak" -Force }
    $json = $Settings | ConvertTo-Json -Depth 64
    [IO.File]::WriteAllText($SettingsPath, $json, (New-Object Text.UTF8Encoding $false))
}

function Set-Prop($Object, [string]$Name, $Value) {
    $Object | Add-Member -NotePropertyName $Name -NotePropertyValue $Value -Force
}

function Get-OrAddObject($Object, [string]$Name) {
    if (-not ($Object.PSObject.Properties.Name -contains $Name) -or -not ($Object.$Name -is [pscustomobject])) {
        Set-Prop $Object $Name ([pscustomobject]@{})
    }
    $Object.$Name
}

function Register-Plugin {
    $s = Read-Settings
    if ($null -eq $s) {
        Warn "$SettingsPath не читается как JSON — не трогаю. Подключи плагин руками (см. INSTALL.md)."
        return
    }
    $markets = Get-OrAddObject $s 'extraKnownMarketplaces'
    $plugins = Get-OrAddObject $s 'enabledPlugins'
    $current = $markets.$MarketplaceName
    $same = $current -and $current.source -and $current.source.source -eq 'directory' -and
            $current.source.path -eq $Repo -and $plugins.$PluginId -eq $true
    if ($same) { Ok "плагин уже зарегистрирован в $SettingsPath"; return }
    Set-Prop $markets $MarketplaceName ([pscustomobject]@{ source = [pscustomobject]@{ source = 'directory'; path = $Repo } })
    Set-Prop $plugins $PluginId $true
    Write-Settings $s
    Ok "плагин $PluginId зарегистрирован в $SettingsPath (старая версия: settings.json.skyrimtools.bak)"
}

function Unregister-Plugin {
    $s = Read-Settings
    if ($null -eq $s) { Warn "$SettingsPath не читается как JSON — убери $PluginId руками"; return }
    $changed = $false
    foreach ($pair in @(@('extraKnownMarketplaces', $MarketplaceName), @('enabledPlugins', $PluginId))) {
        $obj = $s.($pair[0])
        if ($obj -is [pscustomobject] -and ($obj.PSObject.Properties.Name -contains $pair[1])) {
            $obj.PSObject.Properties.Remove($pair[1]); $changed = $true
        }
    }
    if ($changed) { Write-Settings $s; Ok "плагин убран из $SettingsPath" } else { Ok 'плагин не был зарегистрирован' }
}

# ---------------------------------------------------------------- проверки конфликтов

function Test-Conflicts {
    $claudeJson = Join-Path $env:USERPROFILE '.claude.json'
    if (Test-Path -LiteralPath $claudeJson) {
        try {
            $cj = [IO.File]::ReadAllText($claudeJson) | ConvertFrom-Json
            if ($cj.mcpServers -and ($cj.mcpServers.PSObject.Properties.Name -contains 'housecarl')) {
                Warn ('houseCARL уже зарегистрирован в ~/.claude.json своим установщиком: будет два одинаковых сервера. ' +
                      'Убери его: houseCARL-Setup.exe --uninstall --claude (скиллы в этом плагине те же).')
            }
        }
        catch {
            if ([IO.File]::ReadAllText($claudeJson) -match '"housecarl"\s*:\s*\{\s*"type"\s*:\s*"stdio"') {
                Warn 'похоже, houseCARL уже зарегистрирован в ~/.claude.json: проверь, что сервер не запускается дважды.'
            }
        }
    }
    if (Test-Path -LiteralPath (Join-Path $ClaudeDir 'skills\housecarl')) {
        Warn '~/.claude/skills/housecarl уже есть (родной установщик houseCARL): скиллы задублируются. Удали через houseCARL-Setup.exe --uninstall --claude.'
    }
    $s = Read-Settings
    if ($s -and $s.enabledPlugins) {
        foreach ($p in $s.enabledPlugins.PSObject.Properties) {
            if ($p.Name -like 'housecarl@*' -and $p.Value -eq $true) {
                Warn "включён и отдельный плагин $($p.Name): houseCARL запустится дважды. Выключи его в /plugin."
            }
        }
    }
}

function Test-ClaudeCode {
    $found = (Get-Command claude -ErrorAction SilentlyContinue) -or
             (Test-Path -LiteralPath "$env:USERPROFILE\.local\bin\claude.exe") -or
             (Test-Path -LiteralPath "$env:LOCALAPPDATA\AnthropicClaude") -or (Test-Path -LiteralPath $ClaudeDir)
    if (-not $found) {
        Warn 'Claude Code не найден. Поставь его (https://claude.com/claude-code: CLI или приложение Claude Desktop) и запусти setup ещё раз.'
    }
}

# ================================================================ удаление

if ($Uninstall) {
    Step 'Удаление SkyrimTools'
    Unregister-Plugin
    $home_ = Get-UserEnv 'SKYRIM_TOOLS_HOME'
    foreach ($n in $EnvNames) { if (Get-UserEnv $n) { [Environment]::SetEnvironmentVariable($n, $null, 'User'); Ok "переменная $n удалена" } }
    if ($home_ -and (Test-Path -LiteralPath $home_)) {
        if (AskYesNo "Удалить папку установки $home_ (houseCARL, Ghidra, проекты Ghidra)?" $false) {
            Remove-Item -LiteralPath $home_ -Recurse -Force; Ok "$home_ удалена"
        }
        else { Say "   папка оставлена: $home_" }
    }
    Say ''
    Say 'Готово. Перезапусти Claude Code. Папку с репозиторием удали сам, если она больше не нужна.'
    exit 0
}

# ================================================================ сбор параметров

Write-Host 'SkyrimTools — установка' -ForegroundColor Cyan
Say "Репозиторий: $Repo"

if ([Environment]::Is64BitOperatingSystem -eq $false) { Fail 'нужна 64-битная Windows' }
if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { Warn 'ARM64: houseCARL и Ghidra x64 работают через эмуляцию; .NET ставь именно x64' }
foreach ($tool in 'curl.exe', 'tar.exe') {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { Fail "нет $tool (нужна Windows 10 1803 или новее)" }
}
if (-not (Test-Path -LiteralPath (Join-Path $Repo '.claude-plugin\plugin.json'))) { Fail "setup.ps1 должен лежать в корне репозитория SkyrimTools ($Repo)" }

$explicitInstallDir = [bool]$InstallDir
if (-not $InstallDir) { $InstallDir = Get-UserEnv 'SKYRIM_TOOLS_HOME' }
if (-not $InstallDir) { $InstallDir = Join-Path $env:LOCALAPPDATA 'SkyrimTools' }
$InstallDir = [IO.Path]::GetFullPath($InstallDir)

# Свои пути, заданные раньше (например, собранный из исходников houseCARL), уважаются, если -InstallDir не указан явно.
$customHousecarl = if (-not $explicitInstallDir) { Get-UserEnv 'HOUSECARL_EXE' } else { $null }
if ($customHousecarl -and -not (Test-Path -LiteralPath $customHousecarl)) { $customHousecarl = $null }
$ReDir = if (-not $explicitInstallDir -and (Get-UserEnv 'SKYRIM_RE_DIR')) { Get-UserEnv 'SKYRIM_RE_DIR' } else { Join-Path $InstallDir 're' }

# MO2
if (-not $Mo2Dir) { $Mo2Dir = Get-UserEnv 'SKYRIM_MO2_DIR' }
if (-not $Yes -or -not $Mo2Dir) {
    while ($true) {
        $answer = Ask 'Папка Mod Organizer 2, где лежит ModOrganizer.ini (Enter — пропустить, houseCARL спросит сам)' $Mo2Dir
        if (-not $answer) { $Mo2Dir = $null; break }
        if (Test-Path -LiteralPath (Join-Path $answer 'ModOrganizer.ini')) { $Mo2Dir = (Resolve-Path -LiteralPath $answer).Path.TrimEnd('\'); break }
        Say "   в '$answer' нет ModOrganizer.ini. Нужна папка экземпляра (в портативном MO2 — папка с ModOrganizer.exe)."
        if ($Yes) { $Mo2Dir = $null; break }
    }
}
elseif (-not (Test-Path -LiteralPath (Join-Path $Mo2Dir 'ModOrganizer.ini'))) { Fail "в $Mo2Dir нет ModOrganizer.ini" }

$GameDir = Find-GameDir $Mo2Dir
$gameVersion = if ($GameDir) { (Get-Item -LiteralPath (Join-Path $GameDir 'SkyrimSE.exe')).VersionInfo.FileVersion } else { $null }

# houseCARL: релиз или сборка из исходников (релизы до v2.1.2 включительно не открывают экземпляр с gamePath=..\)
$relativeMo2 = [bool]($Mo2Dir -and (Test-Mo2Relative $Mo2Dir))
$FromSource = -not $customHousecarl -and ($HousecarlFromSource -or $relativeMo2)

# Ghidra
$reInstalled = Test-Path -LiteralPath (Join-Path $ReDir 'venv\Scripts\pyghidra-mcp.exe')
if ($Ghidra) { $WantGhidra = $true }
elseif ($NoGhidra) { $WantGhidra = $false }
elseif ($reInstalled) { $WantGhidra = $true }
else {
    Say ''
    Say 'Набор для реверса (Ghidra 12.2 + JDK 25 + pyghidra-mcp, ~2 ГБ) нужен только для SKSE-плагинов и разбора'
    Say 'крашей по адресам. Для ESP-патчей, SPID/KID/SkyPatcher, Papyrus и load order он не нужен.'
    $WantGhidra = AskYesNo 'Ставить набор для реверса?' $false
}

# ---------------------------------------------------------------- план

Step 'План'
Say "   папка установки:  $InstallDir"
Say ("   MO2:              " + $(if ($Mo2Dir) { $Mo2Dir } else { '(не задан — houseCARL спросит при первом запуске)' }))
Say ("   игра:             " + $(if ($GameDir) { "$GameDir (SkyrimSE.exe $gameVersion)" } else { '(не найдена)' }))
Say ("   .NET Runtime 10:  " + $(if (Test-DotNet10) { 'уже есть' } else { 'поставить через winget' }))
Say ("   houseCARL:        " + $(if ($customHousecarl) { "свой: $customHousecarl" }
                               elseif ($FromSource) { "$HousecarlVersion из исходников + фикс относительного gamePath (нужен .NET SDK 10)" }
                               else { "$HousecarlVersion -> $InstallDir\housecarl\server" }))
if ($relativeMo2 -and -not $customHousecarl) { Say '                     (в ModOrganizer.ini относительный gamePath — релиз houseCARL его не откроет)' }
Say ("   реверс (Ghidra):  " + $(if ($WantGhidra) { $ReDir } else { 'не ставить' }))
if ($FilesOnly) { Say '   режим -FilesOnly: переменные окружения и settings.json не трогаю' }
else {
    Say "   переменные:       $($EnvNames -join ', ') (пользовательские)"
    Say "   Claude Code:      $SettingsPath  <- marketplace '$MarketplaceName' + плагин $PluginId"
}
if ($gameVersion -and -not $gameVersion.StartsWith('1.5.97')) {
    Warn "игра $gameVersion, а RE-скиллы и addrlib.py рассчитаны на SE 1.5.97. Остальное работает с любой версией."
}
Test-ClaudeCode
if (-not $Yes) {
    $go = Read-Host 'Enter — начать, q — выйти'
    if ($go.Trim().ToLower() -eq 'q') { Say 'Ничего не сделано.'; exit 0 }
}

New-Item -ItemType Directory -Force $InstallDir | Out-Null

# ================================================================ 1. .NET

Step '1. .NET Runtime 10 (x64)'
if (Test-DotNet10) { Ok 'уже установлен' }
elseif (Test-Winget) {
    Say '   ставлю через winget (может появиться запрос прав администратора) ...'
    Invoke-Native { & winget.exe install --id Microsoft.DotNet.Runtime.10 -e --architecture x64 --accept-package-agreements --accept-source-agreements --silent }
    if (Test-DotNet10) { Ok 'установлен' }
    else { Warn '.NET 10 не встал. Поставь руками x64-версию: https://dotnet.microsoft.com/download/dotnet/10.0 (без него houseCARL не запустится)' }
}
else { Warn 'нет winget. Поставь .NET Runtime 10 x64 руками: https://dotnet.microsoft.com/download/dotnet/10.0' }

# ================================================================ 2. houseCARL

Step '2. houseCARL'
$hcRoot = Join-Path $InstallDir 'housecarl'
$hcExe = Join-Path $hcRoot 'server\housecarl-mcp.exe'
$hcVersionFile = Join-Path $hcRoot 'VERSION'
if ($customHousecarl) { Ok "используется свой сервер из HOUSECARL_EXE: $customHousecarl" }
else {
    $api = if ($HousecarlVersion -eq 'latest') { 'https://api.github.com/repos/Avick3110/houseCARL/releases/latest' }
           else { "https://api.github.com/repos/Avick3110/houseCARL/releases/tags/$HousecarlVersion" }
    try { $release = Invoke-RestMethod -Uri $api -Headers @{ 'User-Agent' = 'SkyrimTools-setup' } }
    catch { Fail "не получилось узнать релиз houseCARL ($api): $($_.Exception.Message)" }
    $tag = $release.tag_name
    $wanted = if ($FromSource) { "$tag+relative-gamepath" } else { $tag }
    $installedTag = if (Test-Path -LiteralPath $hcVersionFile) { (Get-Content -LiteralPath $hcVersionFile -Raw).Trim() } else { '' }
    if ($installedTag -eq $wanted -and (Test-Path -LiteralPath $hcExe)) { Ok "houseCARL $wanted уже установлен" }
    else {
        $running = Get-Process -Name 'housecarl-mcp' -ErrorAction SilentlyContinue |
                   Where-Object { $_.Path -and $_.Path.StartsWith($hcRoot, [StringComparison]::OrdinalIgnoreCase) }
        if ($running) {
            Fail 'houseCARL сейчас запущен (открыт Claude Code). Закрой все сессии Claude Code и запусти setup ещё раз.'
        }
        if ($FromSource) {
            $pkg = Build-HousecarlFromSource $tag
            $serverDir = Join-Path $pkg 'out\server'
        }
        else {
            $asset = $release.assets | Where-Object { $_.name -like 'houseCARL-*.zip' } | Select-Object -First 1
            if (-not $asset) { Fail "в релизе houseCARL $tag нет архива houseCARL-*.zip" }
            $sha = if ($asset.digest -like 'sha256:*') { $asset.digest.Substring(7) } else { $null }
            $zip = Get-File $asset.browser_download_url $sha "houseCARL $tag"
            $unpacked = Join-Path (Split-Path $zip) 'x'
            Expand-Zip $zip $unpacked
            $server = Get-ChildItem -LiteralPath $unpacked -Recurse -Filter 'housecarl-mcp.exe' | Select-Object -First 1
            if (-not $server) { Fail 'в архиве houseCARL не нашёлся housecarl-mcp.exe' }
            $serverDir = Split-Path $server.FullName
            $pkg = Split-Path $serverDir
        }
        if (Test-Path -LiteralPath (Join-Path $hcRoot 'server')) { Remove-Item -LiteralPath (Join-Path $hcRoot 'server') -Recurse -Force }
        New-Item -ItemType Directory -Force $hcRoot | Out-Null
        Copy-Item -LiteralPath $serverDir -Destination (Join-Path $hcRoot 'server') -Recurse -Force
        foreach ($f in 'LICENSE', 'THIRD-PARTY-NOTICES.txt', 'CHANGELOG.md', 'README.md') {
            if (Test-Path -LiteralPath (Join-Path $pkg $f)) { Copy-Item -LiteralPath (Join-Path $pkg $f) -Destination $hcRoot -Force }
        }
        Set-Content -LiteralPath $hcVersionFile -Value $wanted -Encoding ASCII
        Ok "houseCARL $wanted -> $hcRoot\server"
    }
}
New-Item -ItemType Directory -Force (Join-Path $InstallDir 'housecarl-data') | Out-Null

# ================================================================ 3. Ghidra

if ($WantGhidra) {
    Step "3. Набор для реверса -> $ReDir"
    foreach ($d in '', 'projects', 'bins\skyrim') { New-Item -ItemType Directory -Force (Join-Path $ReDir $d) | Out-Null }

    if (Get-ChildItem -LiteralPath $ReDir -Directory -Filter 'jdk-*' -ErrorAction SilentlyContinue) { Ok 'JDK уже есть' }
    else { Expand-Zip (Get-File $Pins.JdkUrl $Pins.JdkSha 'JDK 25 (Temurin, ~200 МБ)') $ReDir; Ok 'JDK 25 распакован' }

    if (Get-ChildItem -LiteralPath $ReDir -Directory -Filter 'ghidra_*_PUBLIC' -ErrorAction SilentlyContinue) { Ok 'Ghidra уже есть' }
    else { Expand-Zip (Get-File $Pins.GhidraUrl $Pins.GhidraSha 'Ghidra 12.2 (~500 МБ, это надолго)') $ReDir; Ok 'Ghidra 12.2 распакована' }

    $venvPy = Join-Path $ReDir 'venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $venvPy)) {
        $py = Find-Python
        if (-not $py -and (Test-Winget)) {
            Say '   подходящего Python 3.10-3.13 нет, ставлю Python 3.13 через winget ...'
            Invoke-Native { & winget.exe install --id Python.Python.3.13 -e --scope user --accept-package-agreements --accept-source-agreements --silent }
            $py = Find-Python
        }
        if (-not $py) { Fail 'нужен Python 3.10-3.13: поставь с https://www.python.org/downloads/ и запусти setup ещё раз' }
        Say "   создаю venv на Python $($py.Version) ..."
        $pyExe = $py.Exe; $pyArgs = $py.Args
        Invoke-Native { & $pyExe @pyArgs -m venv (Join-Path $ReDir 'venv') }
        if (-not (Test-Path -LiteralPath $venvPy)) { Fail 'не удалось создать venv' }
    }
    Say '   ставлю Python-пакеты (pyghidra-mcp тянет много зависимостей, пара минут) ...'
    $req = Join-Path $Repo 'requirements-re.txt'
    Invoke-Native { & $venvPy -m pip install --disable-pip-version-check -q -r $req }
    if ($LASTEXITCODE -ne 0) { Fail "pip install -r $req завершился с ошибкой (вывод выше)" }
    Ok 'pyghidra-mcp, capstone, pefile установлены'

    # ghidrecomp 0.5.9: set_pdb печатает symbol_path до присваивания — любой анализ с .pdb падает. Меняем строки местами.
    $util = Join-Path $ReDir 'venv\Lib\site-packages\ghidrecomp\utility.py'
    if (Test-Path -LiteralPath $util) {
        $text = [IO.File]::ReadAllText($util)
        $pattern = "(?m)^([ \t]*)print\(f'Setting pdb to \{symbol_path\}'\)(\r?\n)[ \t]*symbol_path = Path\(path\)[^\r\n]*"
        if ($text -match $pattern) {
            $text = [regex]::Replace($text, $pattern, '$1symbol_path = Path(path)  # SkyrimTools setup: upstream printed it before assigning$2$1print(f''Setting pdb to {symbol_path}'')')
            [IO.File]::WriteAllText($util, $text, (New-Object Text.UTF8Encoding $false))
            Ok 'ghidrecomp: исправлен set_pdb'
        }
        elseif ($text -match 'symbol_path = Path\(path\)') { Ok 'ghidrecomp: set_pdb уже исправлен' }
        else { Warn 'ghidrecomp: не узнал set_pdb, патч не применён (анализ с .pdb может падать)' }
    }

    $exeCopy = Join-Path $ReDir 'bins\skyrim\SkyrimSE.exe'
    if (Test-Path -LiteralPath $exeCopy) { Ok 'копия SkyrimSE.exe уже есть' }
    elseif ($GameDir) { Copy-Item -LiteralPath (Join-Path $GameDir 'SkyrimSE.exe') -Destination $exeCopy; Ok "SkyrimSE.exe $gameVersion скопирован в bins\skyrim" }
    else { Warn "игра не найдена: положи копию SkyrimSE.exe в $exeCopy сам" }
}
else { Step '3. Набор для реверса — пропущен (поставить потом: setup.cmd -Ghidra)' }

# ================================================================ 4-5. переменные и регистрация

if ($FilesOnly) { Step '4-5. Переменные и регистрация — пропущены (-FilesOnly)' }
else {
    Step '4. Переменные окружения'
    Set-UserEnv 'SKYRIM_TOOLS_REPO' $Repo
    Set-UserEnv 'SKYRIM_TOOLS_HOME' $InstallDir
    if ($Mo2Dir) { Set-UserEnv 'SKYRIM_MO2_DIR' $Mo2Dir }
    if ($GameDir) { Set-UserEnv 'SKYRIM_GAME_DIR' $GameDir }
    if ($WantGhidra) { Set-UserEnv 'SKYRIM_RE_DIR' $ReDir }
    foreach ($n in $EnvNames) { $v = Get-UserEnv $n; if ($v) { Ok "$n = $v" } }

    Step '5. Плагин Claude Code'
    Register-Plugin
}

Test-Conflicts

if ($script:Temp -and (Test-Path -LiteralPath $script:Temp)) { Remove-Item -LiteralPath $script:Temp -Recurse -Force -ErrorAction SilentlyContinue }

# ================================================================ итог

Step 'Готово'
Say '   1. Полностью закрой и снова открой Claude Code (все окна и терминалы), чтобы подхватились переменные.'
Say '   2. В Claude Code: /plugin — должен быть включён skyrim-tools; /mcp — серверы housecarl и pyghidra-mcp.'
if (-not $Mo2Dir) { Say '   3. При первом обращении houseCARL спросит папку MO2 (с ModOrganizer.ini).' }
if ($WantGhidra) {
    Say '   *  Ghidra: первый импорт SkyrimSE.exe анализируется десятки минут. Попроси Claude:'
    Say "      `"импортируй $ReDir\bins\skyrim\SkyrimSE.exe в Ghidra`" и дождись конца анализа."
}
Say '   Обновление: git pull, снова setup.cmd, затем в Claude Code /plugin marketplace update skyrim-tools.'
Say '   Другой агент (Codex, VS Code, Cursor, Windsurf, Cline, Gemini CLI, opencode) — начни с AGENTS.md в папке'
Say '   репозитория; проверка установки: scripts\agents\doctor.ps1 -Fix; конфиг MCP:'
Say '   scripts\agents\connect.ps1 -Client <codex|vscode|cursor|windsurf|cline|gemini|opencode|json>'
if ($script:Warnings.Count) {
    Write-Host ''
    Write-Host 'Предупреждения:' -ForegroundColor Yellow
    foreach ($w in $script:Warnings) { Write-Host "   - $w" -ForegroundColor Yellow }
}
