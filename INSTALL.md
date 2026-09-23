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

From the root of the cloned repository or the unpacked archive:

```bash
mkdir -p ~/.claude/skills
cp -r skill/codex-cli ~/.claude/skills/codex-cli
mkdir -p ~/.claude/codex-cli
cp -r files     ~/.claude/codex-cli/files
cp    README.md ~/.claude/codex-cli/
```

Installing over an earlier version of this package: delete `~/.claude/skills/codex-cli` and
`~/.claude/codex-cli` first, otherwise `cp -r` puts a copy inside them.

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
6. backs up every file before touching it, then adds the rules block to `~/.claude/CLAUDE.md`
   (replacing the old "codex MCP" block or an earlier version of this block), showing the diff;
7. removes the old MCP setup in every scope (user, local, project), the `codex-compact-watcher`
   hook and the old `codex-mcp` skill;
8. runs a smoke test: a new thread, then a continuation of the same thread.

**The rules in `CLAUDE.md` are not a formality.** They hold the thread discipline: continuing a
thread keeps the context and the chance of a prompt-cache hit, while the habit of opening a new
thread for every question pays for the project context again. Do not drop that block.

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
files/CLAUDE.codex.md               the rules block for ~/.claude/CLAUDE.md
files/codex-config.example.toml     excerpt of ~/.codex/config.toml
```

No tokens, keys or personal paths are included.
