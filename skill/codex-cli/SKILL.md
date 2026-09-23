---
name: codex-cli
description: Подключить (подрубить) codex к Claude Code через CLI-обёртку codex-ask - «подруби кодекс», «подключи codex», «настрой codex», «почини codex», «codex mcp сломался». Ставит обёртку ~/.claude/bin/codex-ask, прописывает правила в ~/.claude/CLAUDE.md, снимает остатки старой MCP-связки (codex mcp-server удалён в codex-cli 0.155.1) и проверяет всё дымовым тестом. Вызывать также при поломках codex и для обновления уже установленной связки - скилл идемпотентен и содержит таблицу диагностики.
---

# codex CLI -> Claude Code

Ставит, обновляет и чинит связку «Claude Code спрашивает codex». Файлы пакета лежат рядом с
этим SKILL.md (`files/` на уровень выше `skill/`) либо в `~/.claude/codex-cli/` после установки.
Дальше этот каталог зовётся `$PKG`.

**Ничего не ставь и не переписывай молча.** Каждый шаг, который меняет файл или ставит софт,
сначала показывай, потом делай. Чтение и проверки выполняй сразу.

**Переменные оболочки между вызовами Bash не сохраняются.** Где ниже нужен путь или id из
прошлого шага, подставляй его значение явно.

## 0. Что уже есть

Каталог codex: `CODEX_HOME`, если задан, иначе `~/.codex`, приведённый к абсолютному пути так
же, как это делает обёртка. Дальше он зовётся `$CH`; вычисляй его в каждой команде заново и
экспортируй, чтобы пробы и тесты шли в тот же каталог:

```bash
export CODEX_HOME="$(python3 -c 'import os,pathlib; print(pathlib.Path(os.path.expanduser(os.environ.get("CODEX_HOME") or "~/.codex")).resolve())')"; CH="$CODEX_HOME"
```

Везде ниже и в установленных правилах `~/.codex` означает `$CH`.

Собери картину одной пачкой и покажи пользователю таблицей «есть / нет»:

```bash
export CODEX_HOME="$(python3 -c 'import os,pathlib; print(pathlib.Path(os.path.expanduser(os.environ.get("CODEX_HOME") or "~/.codex")).resolve())')"; CH="$CODEX_HOME"; echo "codex home: $CH"
which codex && codex --version
codex login status
python3 -c 'import sys; print(sys.version); assert sys.version_info >= (3, 7), "нужен Python 3.7+"'
ls -la ~/.claude/bin/codex-ask 2>&1 && grep -n '^DEFAULT_MODEL' ~/.claude/bin/codex-ask
grep -n -E 'codex \(CLI через|codex MCP \(mcp__codex__codex' ~/.claude/CLAUDE.md 2>/dev/null
grep -n -E '^model *=|^model_reasoning_effort *=|web_search' "$CH/config.toml" 2>/dev/null
```

Остатки старой MCP-связки - по имени `codex` **и** по команде `codex mcp-server`, во всех
scope: user и local (`~/.claude.json`), project (`.mcp.json` в корнях проектов), хуки в
пользовательских и проектных настройках:

```bash
python3 - <<'EOF'
import json, pathlib
home = pathlib.Path.home()
def is_codex(name, cfg):
    return name == "codex" or "mcp-server" in json.dumps(cfg) and "codex" in json.dumps(cfg)
cj = home / ".claude.json"
d = json.loads(cj.read_text()) if cj.exists() else {}
print("user:", [n for n, c in d.get("mcpServers", {}).items() if is_codex(n, c)])
projects = d.get("projects", {})
for p, v in projects.items():
    hits = [n for n, c in (v.get("mcpServers") or {}).items() if is_codex(n, c)]
    if hits: print("local", p, hits)
    mj = pathlib.Path(p) / ".mcp.json"
    if mj.is_file():
        try: m = json.loads(mj.read_text())
        except ValueError: continue
        hits = [n for n, c in m.get("mcpServers", {}).items() if is_codex(n, c)]
        if hits: print("project", mj, hits)
settings = [home / ".claude/settings.json", home / ".claude/settings.local.json"]
settings += [pathlib.Path(p) / ".claude" / f for p in projects for f in ("settings.json", "settings.local.json")]
for s in settings:
    if not s.is_file(): continue
    try: st = json.loads(s.read_text())
    except ValueError: continue
    for ev, groups in (st.get("hooks") or {}).items():
        for g in groups:
            for h in g.get("hooks", []):
                if "codex-compact-watcher" in str(h.get("command", "")):
                    print("hook", s, ev, g.get("matcher"))
    env = st.get("env") or {}
    if "MCP_TOOL_TIMEOUT" in env or "CLAUDE_CODE_MCP_TOOL_IDLE_TIMEOUT" in env:
        print("env", s, {k: env.get(k) for k in ("MCP_TOOL_TIMEOUT", "CLAUDE_CODE_MCP_TOOL_IDLE_TIMEOUT")})
EOF
claude mcp list 2>&1 | grep -i codex
ls -d ~/.claude/skills/codex-mcp ~/.claude/codex-mcp ~/.claude/hooks/codex-compact-watcher.py 2>/dev/null
```

Дальше делай только недостающее или устаревшее.

## 1. Резервные копии - до любой правки

Перед первым изменяющим шагом скопируй **каждый** файл, который будешь менять, с уникальным
суффиксом и проверь, что копия легла. Ошибку копирования не глушить:

```bash
set -e
export CODEX_HOME="$(python3 -c 'import os,pathlib; print(pathlib.Path(os.path.expanduser(os.environ.get("CODEX_HOME") or "~/.codex")).resolve())')"
B=$(mktemp -d "$HOME/.claude/codex-cli-backup-$(date +%Y%m%d)-XXXXXX")   # новый каталог на каждый запуск
for f in "$HOME/.claude/CLAUDE.md" "$HOME/.claude/settings.json" "$HOME/.claude.json" \
         "$CODEX_HOME/config.toml" "$HOME/.claude/bin/codex-ask"; do
  if [ -e "$f" ]; then
    dst="$B/$(printf '%s' "$f" | tr '/' '_')"
    cp -p "$f" "$dst" || { echo "BACKUP FAILED: $f"; exit 1; }
    echo "backup: $f -> $dst"
  fi
done
```

Если скрипт напечатал `BACKUP FAILED` или вышел не с 0 - остановись и ничего не меняй.

Проектные `.mcp.json` и `.claude/settings*.json` из шага 0 копируй в тот же каталог `$B` перед
их правкой.
Файла нет - копировать нечего. Скажи пользователю, куда легли копии.

## 2. codex CLI

Нужен `codex` в PATH; связка проверена на `codex-cli 0.155.1`. Если его нет - **не ставь сам**,
предложи и дождись ответа: `npm i -g @openai/codex` или `brew install codex`. На другой версии
работоспособность подтверждает только дымовой тест (шаг 8). Не предлагай откатывать codex ради
`mcp-server`: старые сборки не обслуживают свежие модели.

## 3. Авторизация

`codex login status` должен показать аккаунт. Если нет - **сам залогинить не можешь**, это
интерактивный вход в браузере. Попроси выполнить в этой сессии: `! codex login`.
Нужен ChatGPT-план с доступом к Codex.

## 4. Модель и конфиг codex

Проверь основную и запасную модель на этом аккаунте:

```bash
codex exec --skip-git-repo-check --sandbox read-only --model gpt-6-astra 'ответь одним словом: ok'
codex exec --skip-git-repo-check --sandbox read-only --model gpt-5.6-sol 'ответь одним словом: ok'
```

`--skip-git-repo-check` обязателен: без него `codex exec` откажется работать вне
git-репозитория, и отказ запуска легко принять за отказ модели.

Сначала отличи недоступность модели от временных сбоев: ошибки авторизации, сети или лимита
(`access token`, `rate limit`, таймаут) - не повод менять модель; устрани причину и повтори.
Решение принимай только по ответам и по `... is not supported ...`:

- Обе ответили -> `<MODEL>` = `gpt-6-astra`, `<FALLBACK>` = `gpt-5.6-sol`.
- Ответила только `gpt-6-astra` -> она основная, запасной нет.
- Ответила только `gpt-5.6-sol` -> она основная, запасной нет.
- `... is not supported when using Codex with a ChatGPT account` у обеих -> покажи слаги из
  `$CH/models_cache.json` (поле `slug`) и **спроси**, какие ставить.
- `The '<модель>' model requires a newer version of Codex` -> старый codex, предложи обновить.

В `$CH/config.toml` должны быть `model = "<MODEL>"` и `model_reasoning_effort = "high"`
(пример - `$PKG/files/codex-config.example.toml`; целиком поверх не копировать). Если там
`[features] web_search_request = true` (в 0.155.1 ключ устарел и печатает предупреждение на
каждом вызове) - предложи заменить его на верхнеуровневый `web_search = "live"`, чтобы
сохранить поведение. Уже заданный `web_search` не трогай.

## 5. Обёртка codex-ask

```bash
mkdir -p ~/.claude/bin
cp "$PKG/files/bin/codex-ask" ~/.claude/bin/codex-ask
chmod +x ~/.claude/bin/codex-ask
```

Если `<MODEL>` не `gpt-6-astra` - поправь строку `DEFAULT_MODEL = ...` в начале файла и покажи
её до и после. Затем проверь, что три места согласованы: `DEFAULT_MODEL` в обёртке, `model` в
`$CH/config.toml` и `<MODEL>` в правилах (шаг 6).

## 6. Правила в CLAUDE.md

Возьми `$PKG/files/CLAUDE.codex.md` и заполни плейсхолдеры: `<MODEL>` - основной слаг,
`<FALLBACK>` - запасной. Если запасной нет, удали всё, что о ней говорит: оговорку о запасной в
списке запретов, пункт о переходе на запасную и слова «только по правилу о запасной модели
ниже» в начале раздела о модели. Плейсхолдеров в итоговом тексте остаться не должно:

```bash
FILLED="/путь/к/заполненному/блоку.md"   # подставь реальный путь
if grep -n -E '<MODEL>|<FALLBACK>' "$FILLED"; then echo "ОСТАЛИСЬ ПЛЕЙСХОЛДЕРЫ"; fi
```

Вставка в `~/.claude/CLAUDE.md` (создай файл, если его нет):

- есть блок нового пакета (`## codex (CLI через ...`, до маркера `конец блока codex`) - замени
  его целиком;
- есть блок старого пакета (`## codex MCP (mcp__codex__codex ...`) - замени его новым блоком;
- нет ни того, ни другого - допиши в конец.

Остальные правила пользователя не трогай. Покажи diff.

## 7. Снять старую MCP-связку (если шаг 0 её нашёл)

Показать и после согласия сделать:

- **MCP-записи во всех найденных scope:** `claude mcp remove codex -s user`; для local -
  `claude mcp remove codex -s local`, запущенный из каталога этого проекта; для project -
  `claude mcp remove codex -s project` из корня проекта (это меняет `.mcp.json`, общий для
  команды, - предупреди пользователя). Если запись называлась не `codex`, удаляй по её имени.
  После удаления повтори проверку из шага 0: scope с более высоким приоритетом может скрывать
  ещё одну запись.
- **Хук:** в каждом найденном файле настроек удали из `hooks.PostToolUse[*].hooks` только
  обработчик с `codex-compact-watcher`; группу матчера удаляй, только если она осталась пустой;
  остальные хуки не трогай. Файл `~/.claude/hooks/codex-compact-watcher.py` удаляй, когда на
  него не ссылается ни один файл настроек. Обёртка сама сообщает о сжатии контекста.
- **env:** `MCP_TOOL_TIMEOUT` и `CLAUDE_CODE_MCP_TOOL_IDLE_TIMEOUT` ставил старый пакет ради
  codex. Если других MCP-серверов с долгими вызовами нет - предложи убрать, иначе оставь.
- **Старый пакет:** `~/.claude/skills/codex-mcp` и `~/.claude/codex-mcp`.

Уже открытые окна Claude Code держат запущенный старый `codex mcp-server` до перезапуска - это
нормально.

## 8. Дымовой тест

Одним вызовом Bash (id треда берётся из вывода первого шага):

```bash
set -e -o pipefail
T=$(mktemp -d)
echo 'Запомни число 4242. Ответь одним словом: stored' > "$T/p1.txt"
echo 'Какое число ты запомнил? Ответь только числом.' > "$T/p2.txt"
~/.claude/bin/codex-ask new --dir "$T" "$T/p1.txt" | tee "$T/r1.txt"
ID=$(awk '/^session_id:/{print $2}' "$T/r1.txt")
echo "$ID" | grep -Eq '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' \
  || { echo "SMOKE FAILED: no session id"; exit 1; }
~/.claude/bin/codex-ask resume "$ID" --dir "$T" "$T/p2.txt"
echo "SMOKE OK"
```

Ожидается: оба вызова `status: ok (exit 0)`, у обоих один `session_id`, ответы `stored` и `4242`.
Тогда модель, обёртка и продолжение треда работают.

## 9. Отчёт

Коротко: версия codex, основная и запасная модель, где обёртка, что сделано с CLAUDE.md, что
снято от старой связки, где резервные копии. Напомни главное правило - **один тред на поток
задач**.

## Если сломалось

Подробно - `$PKG/README.md`, раздел «Режимы отказа». Кратко:

| Симптом | Причина | Что делать |
|---|---|---|
| `codex (CONNECTION_CLOSED)` или `stdin is not a terminal` при старте MCP | осталась запись `codex mcp-server`, а в codex 0.155.1+ её нет | шаг 7 |
| `status: FAILED (exit 75)`, `BUSY` | тред занят другим вызовом | дождаться, второй не запускать |
| `... is not supported when using Codex with a ChatGPT account` | неверный слаг | шаг 4 |
| `... requires a newer version of Codex` | CLI старее модели | обновить codex |
| `Your access token could not be refreshed` | протухла авторизация | один повтор, затем `! codex login` |
| `session_id: UNKNOWN`, exit 1 | поток событий не подтвердил тред | смотреть `events.jsonl` в `out_dir` |
| `compactions: unknown` | журнал треда не найден | проверить `CODEX_HOME` и права |
| exit 143 / 130 | обёртку остановили сигналом | codex остановлен, тред свободен; повторить `resume` |
