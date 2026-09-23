---
name: codex-mcp
description: Подключить (подрубить) codex MCP к Claude Code — «подруби кодекс», «подключи codex», «настрой codex mcp», «почини codex». Регистрирует MCP-сервер codex в user-scope, ставит хук слежения за компакцией, прописывает правила работы в ~/.claude/CLAUDE.md и проверяет связку дымовым тестом. Вызывать также при поломках codex MCP — скилл содержит таблицу диагностики.
---

# codex MCP → Claude Code

Ставит и чинит связку «Claude Code спрашивает codex». Все файлы пакета лежат рядом с этим
SKILL.md — в каталоге, откуда скилл установлен (`files/` на уровень выше `skill/`), либо в
`~/.claude/codex-mcp/` после установки. Дальше он зовётся `$PKG`.

**Ничего не ставь и не переписывай молча.** Каждый шаг, который меняет файл или ставит софт,
сначала показывай, потом делай. Исключение — чтение и проверки, их выполняй сразу.

## 0. Что уже есть

Собери картину одной пачкой команд и покажи её пользователю таблицей «есть / нет»:

```bash
which codex && codex --version
codex login status
claude mcp get codex 2>&1 | head -6
python3 -V
```

Дальше — проверки, которые нельзя делать «по наличию файла»: смотри **содержимое**, иначе
пропустишь полуустановку.

```bash
# хук: мало положить файл — он должен быть прописан в settings.json
python3 - <<'EOF'
import json,pathlib
p=pathlib.Path.home()/".claude/settings.json"
s=json.loads(p.read_text()) if p.exists() else {}
env=s.get("env",{})
need={"mcp__codex__codex","mcp__codex__codex-reply"}
hooks=[h for g in s.get("hooks",{}).get("PostToolUse",[])
       if need <= set(str(g.get("matcher","")).split("|"))
       for h in g.get("hooks",[]) if "codex-compact-watcher" in str(h.get("command",""))]
print("файл хука:", (pathlib.Path.home()/".claude/hooks/codex-compact-watcher.py").exists())
print("хук зарегистрирован (matcher на оба инструмента + наш watcher):", bool(hooks))
print("MCP_TOOL_TIMEOUT:", env.get("MCP_TOOL_TIMEOUT"))
print("IDLE_TIMEOUT:", env.get("CLAUDE_CODE_MCP_TOOL_IDLE_TIMEOUT"))
EOF

# блок правил: искать маркер блока, а не слово «codex» где попало
grep -c 'codex MCP (mcp__codex__codex' ~/.claude/CLAUDE.md 2>/dev/null

# модель реально запинена в конфиге codex? (без строк model_reasoning_effort и профилей)
grep -E '^model *=' ~/.codex/config.toml 2>/dev/null
```

В `claude mcp get codex` проверь не только факт регистрации, но и **scope** (`User config`) и
команду (`codex mcp-server`). Локальная регистрация с тем же именем затеняет пользовательскую —
если увидел `Local config`, разберись, какая из них живая, прежде чем добавлять ещё одну.

Дальше делай только недостающее. К дымовому тесту (шаг 6) переходи, только если все проверки
выше дали ожидаемое, — «MCP отвечает» ещё не значит, что хук работает.

## 1. codex CLI

Нужен установленный `codex` (проверено на `codex-cli 0.153.3`). Если его нет — **не ставь сам**,
предложи пользователю вариант и дождись ответа:

- macOS: `brew install codex`
- или npm: `npm i -g @openai/codex`
- или приложение Codex.app (тогда CLI лежит внутри бандла, и `codex` в PATH может не быть —
  пусть пользователь поставит CLI отдельно, MCP-серверу нужен исполняемый файл в PATH)

## 2. Авторизация

`codex login status` должен показать залогиненный аккаунт. Если нет — **ты сам залогинить не
можешь**, это интерактивный браузерный вход. Попроси пользователя выполнить в этой же сессии:

```
! codex login
```

(префикс `!` запускает команду прямо в диалоге Claude Code, вывод придёт в переписку)

Нужен ChatGPT-план с доступом к Codex. API-ключ здесь не используется.

## 3. Выбор модели — сделать до регистрации MCP

Модель пинится в `~/.codex/config.toml` и дублируется в каждом вызове. Проверь, что модель
реально обслуживается на плане пользователя, **через CLI на диске**:

```bash
codex exec --skip-git-repo-check --sandbox read-only \
  --model gpt-6-astra 'ответь одним словом: ok'
```

`--skip-git-repo-check` обязателен: без него `codex exec` откажется работать вне
git-репозитория, и ты примешь отказ запуска за отказ в доступе к модели. Отличай также ошибки
сети и лимитов от «модель недоступна» — это разные диагнозы.

- Ответил → пин `gpt-6-astra`.
- `'gpt-6-astra' is not supported when using Codex with a ChatGPT account` → плану недоступна;
  проверь тем же способом `gpt-5.6-sol` и пинь её. Если и она отказала — покажи пользователю
  список слагов из `~/.codex/models_cache.json` и **спроси**, какую пинить: дальше вслепую
  перебирать не надо.
- `The 'gpt-6-astra' model requires a newer version of Codex` → **не про план**: старый codex.
  `brew upgrade codex` (или npm), потом повтори.

Актуальный список слагов, которые обслуживает аккаунт, — в `~/.codex/models_cache.json`
(поле `slug`; отображаемое имя вроде «GPT-6-Astra» идентификатором **не является**).

Выбранную модель занеси в `~/.codex/config.toml`:

```toml
model = "<выбранный слаг>"
model_reasoning_effort = "xhigh"
```

Пример — `$PKG/files/codex-config.example.toml`. Не копируй его целиком поверх существующего
конфига: у пользователя там свои секции (`projects` с уровнями доверия, `marketplaces`, пути к
бандлам приложения). Возьми только `model` и `model_reasoning_effort`.

## 4. Регистрация MCP-сервера

```bash
claude mcp add codex -s user -- codex mcp-server
```

`-s user` обязателен: сервер должен быть доступен во всех проектах, а не только в текущем.
Проверка: `claude mcp get codex` → `Scope: User config`, `Type: stdio`, `Command: codex`.

## 5. Хук, env и правила

**Хук слежения за компакцией** (зачем — в `$PKG/README.md`):

```bash
mkdir -p ~/.claude/hooks
cp $PKG/files/hooks/codex-compact-watcher.py ~/.claude/hooks/
chmod +x ~/.claude/hooks/codex-compact-watcher.py
```

**Перед первой правкой любого из двух файлов сделай резервную копию** — они рабочие и не твои:

```bash
cp ~/.claude/settings.json ~/.claude/settings.json.bak-$(date +%Y%m%d) 2>/dev/null || true
cp ~/.claude/CLAUDE.md     ~/.claude/CLAUDE.md.bak-$(date +%Y%m%d)     2>/dev/null || true
```

Если файла нет — копировать нечего, это нормально. Скажи пользователю, куда легли копии.

**`~/.claude/settings.json`** — влей блоки из `$PKG/files/settings.snippet.json`, не затирая
чужие ключи. Читай текущий файл, добавляй недостающее, показывай diff перед записью. Нужны:

- `env.MCP_TOOL_TIMEOUT` — потолок на длинный вызов codex;
- `env.CLAUDE_CODE_MCP_TOOL_IDLE_TIMEOUT: "0"` — снимает обрыв по «тишине» на длинных раздумьях;
- `hooks.PostToolUse` с matcher `mcp__codex__codex|mcp__codex__codex-reply`.

Если у пользователя уже есть `hooks.PostToolUse` — добавь ещё один элемент в массив, не
заменяй существующие.

**Правила работы** — содержимое `$PKG/files/CLAUDE.codex.md` допиши в `~/.claude/CLAUDE.md`
(создай файл, если его нет). Там дисциплина модели и тредов и таблица ошибок.

В файле два плейсхолдера — заполни их по итогу шага 3, иначе правила будут противоречивы:

- `<MODEL>` → слаг, который подтвердился (везде, каждое вхождение);
- `<FALLBACK>` → запасной слаг. Если основной моделью стала `gpt-5.6-sol`, запасной у неё уже
  нет — тогда убери из блока абзац про запасную модель целиком, а не оставляй «sol никогда не
  по умолчанию» под пином на sol.

Если блок «codex MCP» в `CLAUDE.md` уже есть — обнови его, а не дублируй.

## 6. Перезапуск и дымовой тест

MCP-сервер стартует вместе с сессией Claude Code: **пока сессию не перезапустили, нового
сервера нет**. Скажи пользователю выйти и зайти (`claude` заново или `--continue`), а после
запуска — выполнить дымовой тест:

1. `claude mcp list` → строка `codex: codex mcp-server - ✔ Connected`
2. Вызов `mcp__codex__codex` с `model` = выбранный слаг, `cwd` = текущий проект,
   `sandbox: "read-only"`, `approval-policy: "never"`, `prompt`: «Ответь одним словом: ok».
   Ответ пришёл → связка рабочая. Запомни `threadId` — дальше только `codex-reply`.

## 7. Отчёт

Скажи коротко: какая модель запинена, где зарегистрирован сервер, встал ли хук, что дописано
в CLAUDE.md, и напомни главное правило — **один threadId на поток задач** (иначе кэш промпта
обнуляется и каждый вызов платит за контекст заново).

## Если сломалось

Полная таблица — в `$PKG/README.md`, раздел «Режимы отказа». Кратко:

| Симптом | Причина | Что делать |
|---|---|---|
| `[Tool result missing due to internal error]` | обёртка Claude Code потеряла результат | бросить тред, начать новый; таймауты не помогают |
| `Session not found for thread_id` | сервер не знает тред (рестарт) | новый тред |
| `... is not supported when using Codex with a ChatGPT account` | неверный слаг модели | шаг 3 |
| `... requires a newer version of Codex` | MCP-сервер старше CLI на диске | проверить `codex exec`, перезапустить сессию |
| `Your access token could not be refreshed` | протухла авторизация | `! codex login` |
