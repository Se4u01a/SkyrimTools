# skyrim-gateway — спецификация MCP-фасада

Статус: **черновик для обсуждения**, кода нет. Решения, помеченные «открыто», ждут владельца репозитория.

## 1. Зачем

Сейчас SkyrimTools — это три MCP-сервера с разными рантаймами и ~20 скриптов, которые агент вызывает через shell:

| Бэкенд | Рантайм | Инструментов | Особенность |
|---|---|---|---|
| houseCARL | .NET 10 | 31 | читает живой экземпляр MO2; пишет плагины и файлы модов |
| pyghidra-mcp | Python venv + JDK 25 + Ghidra 12.2 | 20 | JVM стартует 20–60 с; проект Ghidra блокируется одним процессом |
| SkyLink AI | .NET 10 | 87 | говорит с игрой по `\\.\pipe\SkyrimMCP`; плагин обслуживает **одного клиента за раз** (`PipeServer.cpp`: accept → обслужить до отключения → следующий) |
| scripts/ | Python 3 (stdlib; часть — RE venv) | ~20 CLI | вызываются через shell, вывод — текст или JSON |

Проблемы, которые решает фасад:

1. **Контекст агента.** ~138 MCP-инструментов плюс скрипты. Агент тратит токены на списки и путает похожие инструменты.
2. **Отказы на старте.** Неустановленный бэкенд виден как `CONNECTION_CLOSED`; агент не знает, что это «не установлено», а не «сломалось».
3. **Совместный доступ.** Две сессии агента = два JVM Ghidra на одном проекте (вторая не откроет проект) и два клиента SkyLink (второй ждёт, пока первый отпустит pipe, и падает по таймауту 3 с).
4. **Правила только на словах.** «Не писать в чужой мод», «менять игру только по просьбе», «не трогать сейвы» — сейчас это текст в скиллах; ничто их не применяет.
5. **Установка и диагностика** размазаны по `setup.ps1`, `doctor.ps1`, `connect.ps1`.

## 2. Решения

| Решение | Почему |
|---|---|
| Один exe на Go, без рантайма | ставится копированием; управляет процессами и I/O без зависимостей |
| Бэкенды — **дочерние процессы** на хосте | MO2, игра, pipe и память процесса доступны только с хоста; изоляция зависимостей уже есть: всё портативно лежит в `%SKYRIM_TOOLS_HOME%` |
| Контейнер — **опциональный драйвер, только для Ghidra** | Ghidra работает с копией exe, хост ей не нужен; Docker не обязателен никому |
| Существующие серверы не переписываются | houseCARL и pyghidra-mcp — чужие проекты; фасад их оборачивает |
| Python-скрипты вызываются как подпроцессы, порт на Go — по одному и по желанию | фикстуры `selftest.py` остаются спецификацией поведения |
| Бинарник не хранится в git | репозиторий «без бинарников»: exe собирает CI и прикладывает к GitHub Release, `setup` скачивает его с SHA-256; `go build` из исходников — всегда альтернатива |

Не цели: замена houseCARL, своя реализация чтения записей, удалённый доступ (только loopback), Linux/macOS.

## 3. Архитектура

```
агент A ──stdio──► skyrim-gateway (shim) ──┐
агент B ──stdio──► skyrim-gateway (shim) ──┤  именованный pipe \\.\pipe\skyrim-gateway-<user>
                                           ▼
                                 skyrim-gateway daemon (один на пользователя)
                                   ├─ registry: бэкенды, их состояние, схемы
                                   ├─ policy:   классы инструментов, подтверждения, аудит
                                   ├─ router:   фасадные инструменты -> вызовы бэкендов
                                   └─ backends
                                        ├─ housecarl  (process, stdio)        ленивый, idle-stop 30 мин
                                        ├─ ghidra     (process | container)   ленивый, idle-stop 60 мин, 1 экземпляр
                                        ├─ skylink    (process, stdio)        ленивый, 1 экземпляр, только при живой игре
                                        └─ scripts    (подпроцесс на вызов)
```

- **Shim и daemon — один exe.** `skyrim-gateway` без аргументов — это shim: подключается к daemon, а если его нет, запускает и ждёт готовности. Клиенты MCP прописывают только shim (stdio), как сейчас лаунчеры `.cmd`.
- **Один daemon на пользователя** решает проблему 3: одна JVM Ghidra и одно соединение SkyLink на все сессии. Вызовы к бэкенду с одним экземпляром сериализуются очередью, у каждого вызова свой таймаут.
- **Транспорт shim ↔ daemon** — именованный pipe с ACL «только текущий пользователь». TCP-порт не открывается.
- **Состояния бэкенда:** `not_installed`, `stopped`, `starting`, `ready`, `degraded` (отвечает с ошибками), `failed` (упал N раз подряд), `unavailable` (для SkyLink: игра не запущена). Переходы и причина пишутся в лог.
- **Ленивый старт:** бэкенд поднимается при первом вызове его инструмента. `initialize` и `tools/list` у фасада не запускают ни одного бэкенда: схемы фасадных инструментов статические, схемы сквозных берутся из кэша последнего `tools/list` бэкенда (см. §5).
- **Перезапуск:** при падении — до 3 попыток с паузой 1/5/30 с, затем `failed` до явного `gateway.restart`.
- **Долгие операции** (анализ exe в Ghidra — десятки минут, компиляция Papyrus против MO2 — около минуты): фасад пробрасывает `notifications/progress` и `notifications/cancelled` в обе стороны. Если клиент отключился посреди вызова, daemon доводит вызов до конца и хранит результат 10 мин под `job_id` (`gateway.job`).

## 4. Фасадный API

Принцип: **небольшое курированное ядро всегда в `tools/list`**, всё остальное доступно, но не засоряет контекст.

### 4.1 Ядро (всегда видно, ~25 инструментов)

| Инструмент | Класс | Бэкенд / реализация | Назначение |
|---|---|---|---|
| `gateway.status` | read | daemon | бэкенды, их состояние, версии, что не установлено и какой командой ставится |
| `gateway.discover` | read | daemon | поиск по всем инструментам (ядро + сквозные) по словам; возвращает имена, описания, класс |
| `gateway.enable` | read | daemon | добавить группу сквозных инструментов в `tools/list` сессии (`notifications/tools/list_changed`) |
| `gateway.call` | по цели | router | вызвать любой инструмент по имени — для клиентов без `list_changed` |
| `gateway.job` | read | daemon | статус и результат долгого вызова по `job_id` |
| `loadorder.status` | read | houseCARL `load_order_status` | экземпляр MO2, профиль, игра, число плагинов |
| `records.query` | read | houseCARL `records` | записи, победитель, дерево конфликтов, diff между плагинами |
| `records.check` | read | houseCARL `check` | висячие ссылки, отсутствующие мастера и прочие проверки |
| `assets.which` | read | houseCARL `asset_status` | какой мод выигрывает файл |
| `skse.status` | read | houseCARL `skse` + `scripts/logs/skse_load_status.py` | DLL на диске и что SKSE сделал с ними на последнем запуске |
| `patch.plan` | read | houseCARL (dry run) | план изменения записей: что, куда, в какой новый плагин |
| `patch.apply` | write-mo2 | houseCARL `apply` / `create` / `forward` ... | применить план по `plan_id` (§6) |
| `papyrus.compile` | write-mo2 | `scripts/papyrus/papyrusc.py` | `.psc` -> `.pex` в новую папку мода |
| `papyrus.decompile` | read | houseCARL `decompile_script` / `pexdis.py` | исходник или дизассемблер `.pex` |
| `logs.crash` | read | `scripts/logs/crash_triage.py` | сигнатуры крашей |
| `logs.papyrus` | read | `scripts/logs/papyrus_triage.py` | ошибки Papyrus по формам |
| `logs.mirror` | write-local | `scripts/logs/mirror_logs.py` | append-only копия логов в `%SKYRIM_TOOLS_HOME%` |
| `save.inspect` | read | `scripts/save/ess_scan.py` + `cosave_info.py` | заголовок, плагины, FormID, ко-сейв |
| `plugin.diff` | read | `scripts/esp/espdiff.py` | сравнение двух плагинов по записям |
| `re.address` | read | `scripts/re/addrlib.py` | REL::ID <-> RVA |
| `re.decompile` | read | pyghidra-mcp `decompile_function` | декомпиляция функции (запускает Ghidra) |
| `re.threads` | read | `scripts/re/thread_stacks.py` | снимок потоков зависшей игры |
| `nexus.search` | read | `scripts/misc/nexus_gql.py` / houseCARL `nexus_*` | поиск и страница мода |
| `game.state` | read | SkyLink: несколько read-инструментов за один вызов | игрок, квесты, эффекты, ячейка, меню — одним ответом, с полями по выбору |
| `game.act` | write-game | SkyLink: любой write-инструмент | изменение живой игры по `plan_id` (§6) |

Имена фасада стабильны и не зависят от имён бэкенда. Связь «фасадный инструмент → вызовы бэкенда» описывается в таблице маршрутов в коде, и её проверяет контрактный тест (§9).

### 4.2 Сквозные инструменты (по запросу)

Все инструменты бэкендов доступны под префиксом: `hc.*` (houseCARL), `ghidra.*`, `live.*` (SkyLink). По умолчанию они не в `tools/list`: агент находит их через `gateway.discover` и включает группой через `gateway.enable {"group": "ghidra"}`, либо вызывает через `gateway.call`. Схемы аргументов пробрасываются из `tools/list` бэкенда без изменений, а класс (§6) добавляется фасадом.

### 4.3 Ошибки

Ответ с ошибкой — `isError: true` и структурированное тело:

```json
{"code": "NOT_INSTALLED", "backend": "ghidra", "message": "pyghidra-mcp не установлен",
 "remedy": "skyrim-gateway setup --with ghidra"}
```

| Код | Когда |
|---|---|
| `NOT_INSTALLED` | бинарник или рантайм бэкенда отсутствует |
| `GAME_NOT_RUNNING` | SkyLink: pipe нет, игра не запущена или мод `SkyLink AI` выключен |
| `GAME_UNSAFE` | SkyLink `GetGameSafety`: загрузка, kill move, идёт сохранение (только для write-game) |
| `BACKEND_STARTING` | бэкенд ещё стартует; поле `retry_after_s` |
| `BACKEND_FAILED` | упал N раз; последние строки stderr в `detail` |
| `CONFIRMATION_REQUIRED` | write-вызов без действительного `plan_id` (§6) |
| `POLICY_DENIED` | класс инструмента запрещён конфигом |
| `TIMEOUT` | вызов превысил таймаут; для долгих — `job_id` |
| `INCONCLUSIVE` | скрипт разобрал вход не полностью (exit 1 у `ess_scan`, `espdiff`, `crash_triage`) |

## 5. Схемы и кэш

- После первого успешного `tools/list` бэкенда daemon сохраняет схемы в `%SKYRIM_TOOLS_HOME%\gateway\schemas\<backend>-<version>.json`. `gateway.discover` и сквозной `tools/list` работают по кэшу, не поднимая бэкенд.
- Версия бэкенда — файл `VERSION` из установки (как сейчас у houseCARL, papyrus-compiler и SkyLink). Если версия сменилась, кэш инвалидируется.
- Аннотации MCP (`readOnlyHint`, `destructiveHint`), если бэкенд их даёт, используются как подсказка. Решающая — статическая таблица классов в фасаде (§6), потому что аннотации у бэкендов могут отсутствовать или быть неточными.

## 6. Политика: классы и подтверждения

| Класс | Что | По умолчанию |
|---|---|---|
| `read` | ничего не меняет | разрешено |
| `write-local` | пишет только в `%SKYRIM_TOOLS_HOME%` | разрешено |
| `write-mo2` | создаёт **новую** папку мода или плагин; конфиги houseCARL | двухфазно: `plan` -> `apply` |
| `write-mo2-inplace` | меняет существующий мод или плагин | запрещено, включается только конфигом |
| `write-game` | меняет живую игру (SkyLink write, консоль, Papyrus-вызов с побочным эффектом) | двухфазно + проверка `GAME_UNSAFE` |
| `save` | сохраняет, загружает, удаляет сейв | двухфазно; перезапись или удаление существующего сейва запрещено всегда |

Двухфазный вызов:

1. Инструмент `*.plan` или любой write-инструмент без `plan_id` возвращает план: что изменится, куда, чем откатить. Ответ: `CONFIRMATION_REQUIRED` + `plan_id` (одноразовый, живёт 10 мин, привязан к аргументам по хэшу).
2. Агент показывает план пользователю и после согласия вызывает тот же инструмент с `plan_id`. Другие аргументы — другой хэш — отказ.

Честная граница: это ограждение от случайной записи и лог аудита, а не защита от агента, который решил обойти правила (он может вызвать бэкенд в обход фасада). Аудит: каждая запись — строка JSON в `%SKYRIM_TOOLS_HOME%\gateway\audit.jsonl` (время, сессия, инструмент, аргументы без содержимого файлов, результат).

Статическая классификация houseCARL — **проверить по его коду и `tools/list` при реализации**. Предварительно:
- `read`: `records`, `check`, `asset_status`, `load_order_status`, `skse`, `skypatcher_layer`, `bsa_list`, `nif_inspect`, `decompile_script`, `nexus_*`, `update_status`;
- `write-mo2`: `apply`, `create`, `create_plugin`, `copy`, `forward`, `remove`, `place`, `merge_plugins`, `compact_plugin`, `write_seq`, `nif_set`, `bsa_extract`, `bsa_repack`, `compile_script`, `set_mo2_instance`, `set_tool_path`.

SkyLink: `read`/`write-game`/`save` — по таблице из `skills/skyrim-live-game/SKILL.md`.

## 7. Конфигурация и пути

- `%SKYRIM_TOOLS_HOME%\gateway\config.toml` — необязательный; без него работают значения по умолчанию.
- Существующие переменные (`SKYRIM_TOOLS_HOME`, `SKYRIM_MO2_DIR`, `SKYRIM_GAME_DIR`, `SKYRIM_RE_DIR`, `HOUSECARL_EXE`, `SKYLINK_EXE`, `PAPYRUS_COMPILER_DIR`, `SKYRIM_DOCUMENTS_DIR`) читаются как сейчас; конфиг их только переопределяет. Так лаунчеры `.cmd` и фасад могут жить параллельно.
- Daemon читает **пользовательские** переменные из реестра (`HKCU\Environment`), а не окружение процесса: так он не зависит от устаревшего окружения клиента. Сейчас эту проблему обходят лаунчеры с fallback.

```toml
[policy]
allow_inplace = false          # write-mo2-inplace
allow_game_writes = true       # write-game (всё равно двухфазно)

[backends.ghidra]
driver = "process"             # или "container"
idle_stop_minutes = 60

[backends.skylink]
enabled = true
```

## 8. Установка, doctor, connect

Подкоманды того же exe заменяют три PowerShell-скрипта; `setup.cmd` остаётся тонкой обёрткой для тех, кто привык к нему.

| Команда | Делает |
|---|---|
| `skyrim-gateway setup [--with ghidra,skylink,papyrus] [--mo2 DIR] [--yes]` | план -> подтверждение -> загрузки с проверкой SHA-256 из встроенного манифеста пинов -> переменные -> регистрация в клиентах; повторный запуск = обновление |
| `skyrim-gateway doctor [--json] [--fix]` | всё, что проверяет `doctor.ps1`, плюс живость daemon и бэкендов |
| `skyrim-gateway connect --client claude\|codex\|cursor\|...` | печать или запись конфига клиента: **одна** запись сервера вместо трёх |
| `skyrim-gateway uninstall` | откат всего, что писал setup, включая папку мода `SkyLink AI` с маркером |
| `skyrim-gateway daemon stop\|status\|logs` | управление фоновым процессом |

Манифест пинов (URL, SHA-256, версия) — JSON, встроенный в exe через `go:embed`; он же лежит в репозитории, чтобы его можно было читать и ревьюить. Правила `setup.ps1` сохраняются: план перед действием, идемпотентность, запись только в `%SKYRIM_TOOLS_HOME%`, переменные пользователя и **новые** папки модов MO2.

## 9. Тесты

- **Юнит** (Go): маршрутизация, политика (хэш `plan_id`, истечение, отказ на чужих аргументах), машина состояний бэкенда, очередь для бэкенда с одним экземпляром.
- **Фейковые бэкенды:** маленький stdio MCP-сервер на Go (`internal/fakebackend`) с режимами «медленный старт», «падает», «долгий вызов с progress», «пишет мусор в stdout».
- **Контрактный тест** (`--live`): поднять настоящие houseCARL, pyghidra-mcp и SkyLink, сверить их `tools/list` с таблицей маршрутов и классов. Если у бэкенда появился новый инструмент — его нужно классифицировать, иначе FAIL; если исчез используемый — FAIL.
- **Сценарный тест:** две сессии одновременно вызывают `re.decompile` и `game.state` — один JVM, одно соединение pipe, оба получают ответ.
- `scripts/agents/selftest.py` остаётся проверкой скриптов, а фасадные инструменты-обёртки проверяются теми же синтетическими фикстурами через `gateway.call`.
- CI: `go vet`, `go test ./...`, сборка `windows/amd64` на `windows-latest`; при теге — exe и его SHA-256 в GitHub Release.

## 10. Раскладка в репозитории

```
gateway/
  go.mod                         модуль github.com/Se4u01a/SkyrimTools/gateway
  cmd/skyrim-gateway/main.go
  internal/daemon/               жизненный цикл, pipe shim<->daemon
  internal/backend/              process, container, scripts; машина состояний
  internal/router/               фасадные инструменты, таблица маршрутов
  internal/policy/               классы, plan/apply, аудит
  internal/setup/                setup/doctor/connect/uninstall, манифест пинов
  internal/fakebackend/          для тестов
  pins.json                      манифест загрузок (встраивается)
```

MCP SDK — официальный Go SDK (`github.com/modelcontextprotocol/go-sdk`); версию закрепить при начале работы.

## 11. Этапы

| Этап | Результат | Готово, когда |
|---|---|---|
| 0. Прокси | shim + daemon, три бэкенда сквозными инструментами с префиксами, ленивый старт, коды ошибок, `gateway.status` | Claude Code с одной записью `skyrim-gateway` видит всё, что сейчас дают три сервера; неустановленный Ghidra даёт `NOT_INSTALLED`, а не `CONNECTION_CLOSED`; две сессии делят одну JVM |
| 1. Ядро | §4.1 без write-инструментов, `gateway.discover/enable/call`, кэш схем | в `tools/list` по умолчанию ≤ 30 инструментов; `initialize` не запускает бэкенды; контрактный тест зелёный |
| 2. Политика | классы, plan/apply, аудит, `patch.*`, `game.act`, `papyrus.compile` | write без `plan_id` всегда отказ; in-place запрещён по умолчанию; аудит пишется |
| 3. Установка | `setup/doctor/connect/uninstall` в exe, релиз через CI | чистая Windows: скачать exe -> `setup` -> работает; `setup.ps1` остаётся как fallback один релиз |
| 4. Опции | контейнерный драйвер для Ghidra; перенос горячих скриптов на Go, если подпроцесс Python станет узким местом | по необходимости |

Этапы 0–1 — отдельные PR; после этапа 1 скиллы переводятся на фасадные имена с сохранением старых в скобках на один релиз.

## 12. Открытые вопросы

1. **Имена фасада:** точечные (`records.query`) или с подчёркиванием (`records_query`)? Часть клиентов MCP ограничивает символы в именах; подчёркивание безопаснее.
2. **Где жить фасаду:** в этом репозитории (`gateway/`) или отдельным репозиторием с собственными релизами?
3. **Python:** оставить зависимостью навсегда (скрипты как подпроцессы) или ставить цель «exe + бэкенды, без Python» к этапу 4?
4. **`gateway.enable` и `list_changed`:** проверить, какие из целевых клиентов (Claude Code, Codex, Cursor, VS Code, DSH) реально обновляют список по уведомлению; для остальных — только `gateway.call`.
5. **Совместный доступ к houseCARL:** держит ли он состояние между вызовами (кэш load order, выбранный экземпляр MO2), которое ломается при вызовах из двух сессий через один процесс? Проверить до этапа 0.
6. **DevBench:** подключать как четвёртый бэкенд (HTTP MCP на `127.0.0.1:8920`) или оставить пользователю?
