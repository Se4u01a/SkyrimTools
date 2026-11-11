# Установка SkyrimTools

Набор для моддинга Skyrim SE: скиллы (SPID, KID, SkyPatcher, OAR, Papyrus, SKSE, схемы записей Mutagen, реверс) и
MCP-серверы. С Claude Code он работает как плагин и регистрируется сам, но ничем к нему не привязан: скиллы, скрипты
и серверы те же для любого агента (Codex, VS Code/Copilot, Cursor, Windsurf, Cline, Gemini CLI, opencode) — см.
раздел «Другие агенты» ниже и [AGENTS.md](AGENTS.md).

Три MCP-сервера (третий — по желанию):

- **houseCARL** читает и пишет load order живого экземпляра MO2: записи плагинов, конфликты, патчи в новый ESP,
  (де)компиляция Papyrus, BSA, NIF, поиск на Nexus.
- **pyghidra-mcp** — Ghidra без интерфейса, для декомпиляции SkyrimSE.exe и чужих SKSE-DLL. Ставится по желанию.
- **skylink** — мост к **запущенной** игре через SkyLink AI. Ставится отдельно (`-SkyLink`), без него набор работает как раньше.

Что всё это умеет, с примерами запросов: **[FEATURES.md](FEATURES.md)**.

Docker не нужен: всё работает прямо в Windows, потому что серверу нужны настоящие папки MO2 и игры.

## Что нужно заранее

- Windows 10 (1803+) или 11, x64.
- [Claude Code](https://claude.com/claude-code): консольная версия или вкладка Code в приложении Claude Desktop.
  Вместо него подойдёт любой другой агент — Codex, VS Code с Copilot, Cursor, Windsurf, Cline, Gemini CLI, opencode
  (см. «Другие агенты» ниже).
- Mod Organizer 2 со сборкой Skyrim SE / AE.
- Остальное (.NET 10, Python, Java, Ghidra) установщик поставит сам, через winget и прямые загрузки.

## Установка

1. Скачай репозиторий: `git clone <ссылка>` или ZIP с GitHub (распакуй туда, где он будет лежать постоянно:
   плагин регистрируется по этому пути).
2. Закрой Claude Code.
3. Запусти **`setup.cmd`** двойным щелчком. Он спросит:
   - папку MO2 — ту, где лежит `ModOrganizer.ini` (у портативного MO2 это папка с `ModOrganizer.exe`).
     Можно пропустить, тогда houseCARL спросит её сам при первом обращении;
   - ставить ли набор для реверса (Ghidra, ~2 ГБ). Он нужен только для SKSE-плагинов и разбора крашей по адресам.

   Перед началом установщик покажет план и будет ждать Enter.
4. Открой Claude Code заново и проверь:
   - `/plugin` — включён `skyrim-tools`;
   - `/mcp` — один сервер `skyrim-gateway` в состоянии connected. Он запускает houseCARL, Ghidra и SkyLink по первому
     обращению; какой из них установлен и работает, показывает его инструмент `gateway_status`. exe шлюза
     собирается при первом старте, если установлен Go (https://go.dev/dl/); без Go работает только houseCARL.

Проверка в деле: «какой мод побеждает в записи Iron Sword?» или «напиши SPID, который выдаёт всем бандитам зелье здоровья».

### Параметры

```
setup.cmd -Mo2Dir "D:\Games\MyList\MO2"     папка MO2 без вопроса
setup.cmd -Ghidra                           поставить / доставить набор для реверса
setup.cmd -NoGhidra                         не ставить и не спрашивать
setup.cmd -InstallDir "E:\SkyrimTools"      другая папка установки (по умолчанию %LOCALAPPDATA%\SkyrimTools)
setup.cmd -HousecarlVersion latest          самый свежий релиз houseCARL вместо проверенного
setup.cmd -HousecarlFromSource              собрать houseCARL из исходников (см. ниже про портативные сборки)
setup.cmd -NoPapyrus                        не ставить компилятор Papyrus (тогда нужен Creation Kit)
setup.cmd -SkyLink                          поставить SkyLink AI: сервер + SKSE-плагин в новую папку мода MO2
setup.cmd -Yes                              без вопросов, всё по умолчанию
setup.cmd -Uninstall                        убрать плагин и переменные (папку установки — после вопроса)
```

## Другие агенты (не Claude Code)

Установка та же — `setup.cmd` (шаги 1–3 выше); пункт 4 заменяется на проверку ниже. Ничего из репозитория не
привязано к Claude Code: скиллы — обычные папки с `SKILL.md`, серверы — обычные stdio-MCP, скрипты вызываются
напрямую.

- **С чего начать агенту:** [AGENTS.md](AGENTS.md) — карта репозитория, переменные окружения, MCP-серверы,
  таблица скриптов, правила, которые нельзя нарушать. Его читают Codex и другие агенты, умеющие `AGENTS.md`; для
  остальных в репозитории лежат короткие адаптеры, ссылающиеся на него: `CLAUDE.md`, `GEMINI.md`,
  `.github/copilot-instructions.md`, `.cursor/rules/skyrim-tools.mdc`, `.windsurf/rules/skyrim-tools.md`,
  `.clinerules/skyrim-tools.md`, `llms.txt`.
- **Проверка установки:** `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\agents\doctor.ps1 -Fix` —
  таблица «что есть, чего нет» (houseCARL, .NET 10, MO2, рабочая папка реверса, Python, скиллы) и команды починки.
  `-Json` — то же машинным форматом.
- **Скиллы:** [skills/README.md](skills/README.md) — какой скилл на какой вопрос отвечает и нужен ли ему houseCARL.
  Агент читает `SKILL.md` целиком, а не по имени файла. В Claude Code скилл называется `housecarl:<имя>`, в остальных
  хостах — просто имя папки. Ссылки на все скиллы в папке агента (например `~\.codex\skills`):
  `scripts\agents\connect.ps1 -Client codex -LinkSkills`; для Claude Code `-Client claude`, для любой другой папки
  `-SkillsTarget <путь>`.
- **MCP-серверы:** [docs/mcp-clients.md](docs/mcp-clients.md) — готовые конфиги для Codex, VS Code/Copilot, Cursor,
  Windsurf, Cline, Gemini CLI, opencode. Печатает блок с путями этой машины:
  `scripts\agents\connect.ps1 -Client <codex|vscode|cursor|windsurf|cline|gemini|opencode|json>`.
- **VS Code:** в репозитории уже есть `.vscode/mcp.json`, `houseCARL` и `pyghidra-mcp` подхватываются при открытии папки.

Проверка в деле та же: «какой мод побеждает в записи Iron Sword?» — если сервер подключён, агент ответит по живой
сборке, а не по догадке.

## Что и куда ставится

| Что | Куда |
|---|---|
| houseCARL (сервер из [релиза](https://github.com/Avick3110/houseCARL/releases), SHA-256 проверяется) | `%LOCALAPPDATA%\SkyrimTools\housecarl\server` |
| настройки houseCARL (сохранённый экземпляр MO2) | `%LOCALAPPDATA%\SkyrimTools\housecarl-data` |
| компилятор Papyrus [papyrus-compiler](https://github.com/russo-2025/papyrus-compiler) (MIT, ~1 МБ, SHA-256 проверяется; без `-NoPapyrus`) | `%LOCALAPPDATA%\SkyrimTools\papyrus-compiler` |
| ванильные заголовки Papyrus, сгенерированные из `Skyrim - Misc.bsa` при первой компиляции | `%LOCALAPPDATA%\SkyrimTools\papyrus-headers` |
| JDK 25, Ghidra 12.2, Python venv, проекты Ghidra, копия SkyrimSE.exe (только `-Ghidra`) | `%LOCALAPPDATA%\SkyrimTools\re` |
| .NET Runtime 10; при необходимости .NET SDK 10 и Python 3.13 | через winget, системно |
| переменные `SKYRIM_TOOLS_REPO`, `SKYRIM_TOOLS_HOME`, `SKYRIM_MO2_DIR`, `SKYRIM_GAME_DIR`, `SKYRIM_RE_DIR` | переменные пользователя |
| регистрация плагина | `%USERPROFILE%\.claude\settings.json` (рядом — `settings.json.skyrimtools.bak`) |
| SkyLink AI, сервер (только `-SkyLink`, SHA-256 проверяется) | `%LOCALAPPDATA%\SkyrimTools\skylink\server` |
| SkyLink AI, SKSE-плагин (только `-SkyLink`) | новая папка мода MO2 `SkyLink AI` — включить её в MO2 нужно самому |

Мод `SkyLink AI` установщик кладёт выключенным: включи его в левой панели MO2 (F5 — обновить список) и запускай игру через SKSE.

houseCARL пишет только новые плагины в новые папки модов MO2, и ничего не начинает действовать, пока ты сам не
включишь такой мод в MO2.

## Обновление

```
git pull
setup.cmd
```

Затем в Claude Code: `/plugin marketplace update skyrim-tools` и перезапуск. Claude Code запускает плагин из своей
копии, поэтому без этой команды новые скиллы не появятся. Другим агентам ничего обновлять не нужно: они читают скиллы
из этого репозитория (или из junction-ссылок `connect.ps1`) — достаточно перезапустить сессию.

## Если что-то не так

- **`housecarl` failed в `/mcp`.** Обычно нет .NET Runtime 10 x64: поставь его с
  https://dotnet.microsoft.com/download/dotnet/10.0 (именно x64). Если ругается «houseCARL not found», запусти `setup.cmd` ещё раз.
- **Портативная сборка MO2 (`gamePath=..\` в `ModOrganizer.ini`).** Релиз houseCARL v2.1.2 такой путь не понимает
  (пишет «the game Data folder is missing»). Установщик замечает это сам и собирает houseCARL из исходников того же
  тега с исправлением: ставит .NET SDK 10 через winget, сборка занимает около минуты.
- **Переменные не подхватились.** Закрой все окна Claude Code и терминалов: новые переменные видят только процессы,
  запущенные после установки. В крайнем случае выйди из Windows и зайди снова.
- **Уже ставил houseCARL его родным `houseCARL-Setup.exe`.** Тогда сервер и скиллы задвоятся, установщик об этом
  предупредит. Убери ту копию: `houseCARL-Setup.exe --uninstall --claude`.
- **`pyghidra-mcp` долго стартует.** JVM поднимается 20–60 секунд, это нормально. Первый анализ SkyrimSE.exe
  занимает десятки минут, дальше результат хранится в проекте.
- **Игра AE (1.6.x).** Всё, кроме RE-скилла, работает. RE-скрипты (`addrlib.py` и соседи) рассчитаны на SE 1.5.97.
- **`skylink` подключён, но инструменты не отвечают.** Сервер стартует без игры; ответы идут, только когда игра запущена через SKSE, сейв загружен, а мод `SkyLink AI` включён в MO2 (канал `\\.\pipe\SkyrimMCP`). На 1.5.97 мост не проверен, upstream заявляет AE 1.6.1130+.
- **Скиллы ссылаются на `D:\Games\Issen\...`.** Это проекты автора (IssenFramework, RDF). У тебя их нет, а Claude
  предупреждён, что эти разделы описывают чужую машину.
- **Другой агент не видит MCP-серверы.** Сначала запусти лаунчер руками: `scripts\run_housecarl.cmd` (или
  `scripts\re\run_ghidra_mcp.cmd`) — он печатает, чего не хватает. Потом сверь пути с выводом
  `scripts\agents\doctor.ps1 -Fix` и посмотри конфиг своего клиента в [docs/mcp-clients.md](docs/mcp-clients.md).
- **Агент не читает `AGENTS.md`.** Так бывает у клиентов с фиксированным именем файла инструкций: у Claude Code это
  `CLAUDE.md`, у Gemini CLI — `GEMINI.md`, у Copilot — `.github/copilot-instructions.md`, у Cursor — `.cursor/rules/`,
  у Windsurf — `.windsurf/rules/`, у Cline — `.clinerules/`. Все они уже в репозитории и ссылаются на `AGENTS.md`;
  если твой агент живёт в другом проекте, скопируй туда короткий блок из начала `AGENTS.md` или укажи путь к
  `<папка SkyrimTools>\AGENTS.md`.
