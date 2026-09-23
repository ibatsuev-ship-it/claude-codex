---
name: codex-cli
description: Connect codex to Claude Code through the codex-ask CLI wrapper - "set up codex", "connect codex", "configure codex", "fix codex", "codex mcp is broken" (also in Russian - «подруби кодекс», «подключи codex», «почини codex»). Installs the ~/.claude/bin/codex-ask wrapper, writes the rules into ~/.claude/CLAUDE.md, removes leftovers of the old MCP setup (codex mcp-server was removed in codex-cli 0.155.1) and verifies everything with a smoke test. Also use it when codex breaks and to update an existing installation - the skill is idempotent and has a diagnostics table.
---

# codex CLI -> Claude Code

Installs, updates and repairs the "Claude Code asks codex" link. The package files are next to
this SKILL.md (`files/` one level above `skill/`) or in `~/.claude/codex-cli/` after installation.
That directory is called `$PKG` below.

**Install and rewrite nothing silently.** Every step that changes a file or installs software is
shown first, then done. Reads and checks run immediately.

**Shell variables do not survive between Bash calls.** Where a path or id from a previous step is
needed below, substitute its value explicitly.

## 0. What is already there

The codex directory: `CODEX_HOME` if set, otherwise `~/.codex`, resolved to an absolute path the
same way the wrapper does it. It is called `$CH` below; compute it again in every command and
export it, so that probes and tests use the same directory:

```bash
export CODEX_HOME="$(python3 -c 'import os,pathlib; print(pathlib.Path(os.path.expanduser(os.environ.get("CODEX_HOME") or "~/.codex")).resolve())')"; CH="$CODEX_HOME"
```

Everywhere below and in the installed rules, `~/.codex` means `$CH`.

Collect the picture in one batch and show it to the user as a "present / missing" table:

```bash
export CODEX_HOME="$(python3 -c 'import os,pathlib; print(pathlib.Path(os.path.expanduser(os.environ.get("CODEX_HOME") or "~/.codex")).resolve())')"; CH="$CODEX_HOME"; echo "codex home: $CH"
which codex && codex --version
codex login status
python3 -c 'import sys; print(sys.version); assert sys.version_info >= (3, 7), "Python 3.7+ required"'
ls -la ~/.claude/bin/codex-ask 2>&1 && grep -n '^DEFAULT_MODEL' ~/.claude/bin/codex-ask
grep -n -E 'codex \(CLI through|codex \(CLI через|codex MCP \(mcp__codex__codex' ~/.claude/CLAUDE.md 2>/dev/null
grep -n -E '^model *=|^model_reasoning_effort *=|web_search' "$CH/config.toml" 2>/dev/null
```

Leftovers of the old MCP setup - by the name `codex` **and** by the command `codex mcp-server`, in
every scope: user and local (`~/.claude.json`), project (`.mcp.json` in project roots), hooks in
user and project settings:

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

From here on, do only what is missing or outdated.

## 1. Backups - before any edit

Before the first modifying step, copy **every** file you are going to change, with a unique
suffix, and verify the copy landed. Do not swallow a copy error:

```bash
set -e
export CODEX_HOME="$(python3 -c 'import os,pathlib; print(pathlib.Path(os.path.expanduser(os.environ.get("CODEX_HOME") or "~/.codex")).resolve())')"
B=$(mktemp -d "$HOME/.claude/codex-cli-backup-$(date +%Y%m%d)-XXXXXX")   # a new directory on every run
for f in "$HOME/.claude/CLAUDE.md" "$HOME/.claude/settings.json" "$HOME/.claude.json" \
         "$CODEX_HOME/config.toml" "$HOME/.claude/bin/codex-ask"; do
  if [ -e "$f" ]; then
    dst="$B/$(printf '%s' "$f" | tr '/' '_')"
    cp -p "$f" "$dst" || { echo "BACKUP FAILED: $f"; exit 1; }
    echo "backup: $f -> $dst"
  fi
done
```

If the script printed `BACKUP FAILED` or exited non-zero, stop and change nothing.

Copy the project-level `.mcp.json` and `.claude/settings*.json` files found in step 0 into the
same `$B` directory before editing them.
A file that does not exist has nothing to back up. Tell the user where the copies went.

## 2. codex CLI

`codex` must be in PATH; the link is verified with `codex-cli 0.155.1`. If it is missing, **do not
install it yourself** - propose and wait for an answer: `npm i -g @openai/codex` or
`brew install codex`. On any other version only the smoke test (step 8) confirms it works. Do not
propose downgrading codex to get `mcp-server` back: older builds do not serve current models.

## 3. Authentication

`codex login status` must show an account. If it does not, **you cannot log in yourself** - it is
an interactive browser login. Ask the user to run in this session: `! codex login`.
A ChatGPT plan with Codex access is required.

## 4. Model and codex config

Check the primary and the fallback model on this account:

```bash
codex exec --skip-git-repo-check --sandbox read-only --model gpt-6-astra 'reply with one word: ok'
codex exec --skip-git-repo-check --sandbox read-only --model gpt-5.6-sol 'reply with one word: ok'
```

`--skip-git-repo-check` is mandatory: without it `codex exec` refuses to run outside a git
repository, and that refusal is easy to mistake for a model refusal.

First separate model unavailability from transient failures: auth, network or rate-limit errors
(`access token`, `rate limit`, timeout) are no reason to change the model; fix the cause and
retry. Decide only by the answers and by `... is not supported ...`:

- Both answered -> `<MODEL>` = `gpt-6-astra`, `<FALLBACK>` = `gpt-5.6-sol`.
- Only `gpt-6-astra` answered -> it is the primary, there is no fallback.
- Only `gpt-5.6-sol` answered -> it is the primary, there is no fallback.
- `... is not supported when using Codex with a ChatGPT account` for both -> show the slugs from
  `$CH/models_cache.json` (field `slug`) and **ask** which ones to use.
- `The '<model>' model requires a newer version of Codex` -> old codex, propose an update.

`$CH/config.toml` must contain `model = "<MODEL>"` and `model_reasoning_effort = "high"` (example:
`$PKG/files/codex-config.example.toml`; do not copy it over the whole file). If it has
`[features] web_search_request = true` (deprecated in 0.155.1, prints a warning on every call),
propose replacing it with the top-level `web_search = "live"` to keep the behaviour. Do not touch
an already set `web_search`.

## 5. The codex-ask wrapper

```bash
mkdir -p ~/.claude/bin
cp "$PKG/files/bin/codex-ask" ~/.claude/bin/codex-ask
chmod +x ~/.claude/bin/codex-ask
```

If `<MODEL>` is not `gpt-6-astra`, edit the `DEFAULT_MODEL = ...` line at the top of the file and
show it before and after. Then check that three places agree: `DEFAULT_MODEL` in the wrapper,
`model` in `$CH/config.toml` and `<MODEL>` in the rules (step 6).

## 6. Rules in CLAUDE.md

Take `$PKG/files/CLAUDE.codex.md` and fill in the placeholders: `<MODEL>` - the primary slug,
`<FALLBACK>` - the fallback. If there is no fallback, delete everything that mentions it: the note
in the list of forbidden values, the item about switching to the fallback, and the words "only
under the fallback rule below" at the start of the model section. No placeholders may remain in
the final text:

```bash
FILLED="/path/to/filled/block.md"   # substitute the real path
if grep -n -E '<MODEL>|<FALLBACK>' "$FILLED"; then echo "PLACEHOLDERS LEFT"; fi
```

Insertion into `~/.claude/CLAUDE.md` (create the file if it does not exist):

- a block from this package exists (`## codex (CLI through ...` or the older Russian
  `## codex (CLI через ...`, up to the marker `end of codex block` or `конец блока codex`) -
  replace it entirely;
- a block from the old package exists (`## codex MCP (mcp__codex__codex ...`) - replace it with
  the new block;
- neither - append to the end.

Do not touch the user's other rules. Show the diff.

## 7. Remove the old MCP setup (if step 0 found it)

Show, and after consent do:

- **MCP entries in every scope found:** `claude mcp remove codex -s user`; for local -
  `claude mcp remove codex -s local` run from that project's directory; for project -
  `claude mcp remove codex -s project` from the project root (this changes `.mcp.json`, which is
  shared with the team - warn the user). If the entry was not named `codex`, remove it by its
  name. After removal repeat the check from step 0: a higher-priority scope may hide another entry.
- **Hook:** in every settings file found, remove from `hooks.PostToolUse[*].hooks` only the handler
  with `codex-compact-watcher`; remove the matcher group only if it is left empty; leave the other
  hooks alone. Delete `~/.claude/hooks/codex-compact-watcher.py` once no settings file references
  it. The wrapper reports context compaction itself.
- **env:** `MCP_TOOL_TIMEOUT` and `CLAUDE_CODE_MCP_TOOL_IDLE_TIMEOUT` were set by the old package
  for codex. If there are no other MCP servers with long calls, propose removing them; otherwise
  leave them.
- **Old package:** `~/.claude/skills/codex-mcp` and `~/.claude/codex-mcp`.

Claude Code windows that are already open keep the old `codex mcp-server` running until they are
restarted - that is normal.

## 8. Smoke test

In one Bash call (the thread id is taken from the first step's output):

```bash
set -e -o pipefail
T=$(mktemp -d)
echo 'Remember the number 4242. Reply with one word: stored' > "$T/p1.txt"
echo 'Which number did you remember? Reply with the number only.' > "$T/p2.txt"
~/.claude/bin/codex-ask new --dir "$T" "$T/p1.txt" | tee "$T/r1.txt"
ID=$(awk '/^session_id:/{print $2}' "$T/r1.txt")
echo "$ID" | grep -Eq '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' \
  || { echo "SMOKE FAILED: no session id"; exit 1; }
~/.claude/bin/codex-ask resume "$ID" --dir "$T" "$T/p2.txt"
echo "SMOKE OK"
```

Expected: both calls `status: ok (exit 0)`, the same `session_id` in both, the answers `stored`
and `4242`. Then the model, the wrapper and thread continuation all work.

## 9. Report

Briefly: codex version, primary and fallback model, where the wrapper is, what was done to
CLAUDE.md, what was removed from the old setup, where the backups are. Remind the user of the main
rule - **one thread per task flow**.

## If it breaks

Details: `$PKG/README.md`, section "Failure modes". In short:

| Symptom | Cause | What to do |
|---|---|---|
| `codex (CONNECTION_CLOSED)` or `stdin is not a terminal` at MCP startup | a `codex mcp-server` entry is still registered, and codex 0.155.1+ has no such subcommand | step 7 |
| `status: FAILED (exit 75)`, `BUSY` | the thread is in use by another call | wait; do not start a second one |
| `... is not supported when using Codex with a ChatGPT account` | wrong slug | step 4 |
| `... requires a newer version of Codex` | the CLI is older than the model | update codex |
| `Your access token could not be refreshed` | auth expired | retry once, then `! codex login` |
| `session_id: UNKNOWN`, exit 1 | the event stream did not confirm the thread | look at `events.jsonl` in `out_dir` |
| `compactions: unknown` | the thread log was not found | check `CODEX_HOME` and permissions |
| exit 143 / 130 | the wrapper was stopped by a signal | codex is stopped, the thread is free; run `resume` again |
