# Установка SkyrimTools

Плагин для [Claude Code](https://claude.com/claude-code): скиллы (SPID, KID, SkyPatcher, OAR, Papyrus, SKSE,
схемы записей Mutagen, реверс) и MCP-серверы:

- **houseCARL** читает и пишет load order живого экземпляра MO2: записи плагинов, конфликты, патчи в новый ESP,
  (де)компиляция Papyrus, BSA, NIF, поиск на Nexus.
- **pyghidra-mcp** — Ghidra без интерфейса, для декомпиляции SkyrimSE.exe и чужих SKSE-DLL. Ставится по желанию.

Docker не нужен: всё работает прямо в Windows, потому что серверу нужны настоящие папки MO2 и игры.

## Что нужно заранее

- Windows 10 (1803+) или 11, x64.
- [Claude Code](https://claude.com/claude-code): консольная версия или вкладка Code в приложении Claude Desktop.
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
   - `/mcp` — серверы `housecarl` (и `pyghidra-mcp`, если ставил Ghidra) в состоянии connected.

Проверка в деле: «какой мод побеждает в записи Iron Sword?» или «напиши SPID, который выдаёт всем бандитам зелье здоровья».

### Параметры

```
setup.cmd -Mo2Dir "D:\Games\MyList\MO2"     папка MO2 без вопроса
setup.cmd -Ghidra                           поставить / доставить набор для реверса
setup.cmd -NoGhidra                         не ставить и не спрашивать
setup.cmd -InstallDir "E:\SkyrimTools"      другая папка установки (по умолчанию %LOCALAPPDATA%\SkyrimTools)
setup.cmd -HousecarlVersion latest          самый свежий релиз houseCARL вместо проверенного
setup.cmd -HousecarlFromSource              собрать houseCARL из исходников (см. ниже про портативные сборки)
setup.cmd -Yes                              без вопросов, всё по умолчанию
setup.cmd -Uninstall                        убрать плагин и переменные (папку установки — после вопроса)
```

## Что и куда ставится

| Что | Куда |
|---|---|
| houseCARL (сервер из [релиза](https://github.com/Avick3110/houseCARL/releases), SHA-256 проверяется) | `%LOCALAPPDATA%\SkyrimTools\housecarl\server` |
| настройки houseCARL (сохранённый экземпляр MO2) | `%LOCALAPPDATA%\SkyrimTools\housecarl-data` |
| JDK 25, Ghidra 12.2, Python venv, проекты Ghidra, копия SkyrimSE.exe (только `-Ghidra`) | `%LOCALAPPDATA%\SkyrimTools\re` |
| .NET Runtime 10; при необходимости .NET SDK 10 и Python 3.13 | через winget, системно |
| переменные `SKYRIM_TOOLS_REPO`, `SKYRIM_TOOLS_HOME`, `SKYRIM_MO2_DIR`, `SKYRIM_GAME_DIR`, `SKYRIM_RE_DIR` | переменные пользователя |
| регистрация плагина | `%USERPROFILE%\.claude\settings.json` (рядом — `settings.json.skyrimtools.bak`) |

houseCARL пишет только новые плагины в новые папки модов MO2, и ничего не начинает действовать, пока ты сам не
включишь такой мод в MO2.

## Обновление

```
git pull
setup.cmd
```

Затем в Claude Code: `/plugin marketplace update skyrim-tools` и перезапуск. Claude Code запускает плагин из своей
копии, поэтому без этой команды новые скиллы не появятся.

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
- **Скиллы ссылаются на `D:\Games\Issen\...`.** Это проекты автора (IssenFramework, RDF). У тебя их нет, а Claude
  предупреждён, что эти разделы описывают чужую машину.
