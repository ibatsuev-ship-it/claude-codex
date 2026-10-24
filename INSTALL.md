# Connecting codex to Claude Code - installation

The package sets up a link in which Claude Code can ask codex while it works: "does codex agree?".
How it is built is in `README.md`. This file is installation only.

Two steps: put the files in place, then tell Claude "set up codex" - it does the rest itself and
shows what it changes. If the earlier `codex-mcp-integration` package was installed, the same step
removes it.

## 0. Prerequisites

- **Claude Code**.
- **Codex access** on a ChatGPT plan (`codex login`). Accounts are personal - no tokens ship with
  the package.
- **codex CLI** (verified with `codex-cli 0.155.1`; on any other version only the smoke test
  confirms it works): `npm i -g @openai/codex` or `brew install codex`.
  If you use the Codex.app desktop application, the CLI is still needed separately, in PATH.
- **Python 3.7+** for the wrapper, standard library only.
- macOS or Linux.

## 1. Put the files in place

Installing over an earlier version of this package: first move the old copies aside, otherwise
`cp -r` puts the new files inside them and the old ones stay in use. Each directory is moved on its
own, so a partial installation is handled too:

```bash
B=~/.claude/codex-cli-backup-$(date +%Y%m%d-%H%M%S)
if mkdir -p "$B"; then
  if [ -e ~/.claude/skills/codex-cli ]; then mv ~/.claude/skills/codex-cli "$B/skill" || echo "MOVE FAILED: skill"; fi
  if [ -e ~/.claude/codex-cli ];        then mv ~/.claude/codex-cli        "$B/pkg"   || echo "MOVE FAILED: pkg"; fi
  ls -la "$B"
else
  echo "MOVE FAILED: cannot create $B"
fi
```

On `MOVE FAILED` stop and copy nothing. The skill uses `$B/pkg` to migrate an older rules block.
The installed rules (`~/.claude/codex-rules.md`) live outside these directories, so the import in
`CLAUDE.md` keeps working until the skill rewrites the file.

Then, from the root of the cloned repository or the unpacked archive:

```bash
mkdir -p ~/.claude/skills
cp -r skill/codex-cli ~/.claude/skills/codex-cli
mkdir -p ~/.claude/codex-cli
cp -r files     ~/.claude/codex-cli/files
cp    README.md ~/.claude/codex-cli/
```

## 2. Restart Claude Code

Skills are picked up when a session starts.

## 3. Say "set up codex"

```
set up codex
```

(or explicitly: `/codex-cli`)

Claude goes through the steps itself:

1. checks what is installed and what is missing, finds leftovers of the old MCP setup, shows a table;
2. if the CLI is missing, proposes the install command and **waits for consent**;
3. if not logged in, asks you to run `! codex login`;
4. checks which model the plan actually serves and pins it;
5. installs the wrapper `~/.claude/bin/codex-ask`;
6. backs up every file before touching it, writes the rules to `~/.claude/codex-rules.md` and
   adds one import line for it to `~/.claude/CLAUDE.md`. If `CLAUDE.md` still holds an inline
   rules block (an earlier version of this package or the old "codex MCP" block), it finds your
   personal changes in it, proposes them as local overrides under the import and replaces the
   block - showing every diff and waiting for consent;
7. removes the old MCP setup in every scope (user, local, project), the `codex-compact-watcher`
   hook and the old `codex-mcp` skill;
8. runs a smoke test: a new thread, then a continuation of the same thread.

**The rules are not a formality.** They hold the thread discipline: continuing a thread keeps the
context and the chance of a prompt-cache hit, while the habit of opening a new thread for every
question pays for the project context again. Do not drop the import.

`~/.claude/codex-rules.md` is overwritten on every update - do not edit it. Your own codex rules
(a different default effort, things to leave alone) go to `~/.claude/CLAUDE.md`, under the import
line, in the "Local overrides" list.

## 4. Check that it is alive

```bash
TMP=$(mktemp -d); echo 'Reply with one word: ok' > "$TMP/p.txt"
~/.claude/bin/codex-ask new --dir "$TMP" "$TMP/p.txt"
```

Expect `status: ok (exit 0)` and the answer `ok`. From then on it is enough to ask in the
conversation: "ask codex whether it agrees with this code".

## If something breaks

Say "fix codex" - the same skill has a diagnostics table. Error details are in `README.md`,
section "Failure modes".

## Package contents

```
INSTALL.md                          this file
README.md                           how the link is built, failure modes
skill/codex-cli/SKILL.md            the "set up codex" skill - install, migrate, repair
files/bin/codex-ask                 the codex wrapper
files/CLAUDE.codex.md               the rules, installed as ~/.claude/codex-rules.md
files/legacy/CLAUDE.codex.v1.md     the old inline block, used to migrate earlier installs
files/codex-config.example.toml     excerpt of ~/.codex/config.toml
```

No tokens, keys or personal paths are included.
