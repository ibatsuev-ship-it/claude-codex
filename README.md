# codex in Claude Code through the CLI - how it works

A setup in which Claude Code asks **codex** (OpenAI) while it works: a second opinion on code,
a check of its reasoning, two models arguing over one diff. The typical request: "does codex agree?".

Installation is in `INSTALL.md`. This file covers the design and the failure modes.

The earlier MCP version of this package has been removed from the repository: it does not work
with `codex-cli 0.155.1`. Its last revision is available under the tag `mcp-2026-09-07`.

## Why not MCP

The earlier package (`codex-mcp-integration`, 2026-09-07, tag `mcp-2026-09-07`) connected codex
as an MCP server (`codex mcp-server`). `codex-cli 0.155.1` (2026-09-22) removed that subcommand:
`codex mcp-server` now falls through to the interactive TUI and dies with
`stdin is not a terminal`, and Claude Code reports `codex (CONNECTION_CLOSED)` at startup.
Restarting the session does not help.

There is no replacement for the MCP mode: `codex app-server` is a JSON-RPC daemon with its own
protocol, and Claude Code cannot attach it as an MCP server. Downgrading codex brings
`mcp-server` back, but older builds do not serve current models (that happened with
`gpt-6-astra` on 2026-09-05). So codex is run as an ordinary program through Bash, via the
`codex-ask` wrapper.

## Components

| Component | Where | Purpose |
|---|---|---|
| `codex` CLI | in PATH (`npm i -g @openai/codex` or brew) | the Codex client itself |
| auth | `~/.codex/auth.json` | ChatGPT plan, `codex login` |
| codex config | `~/.codex/config.toml` | default model and reasoning effort |
| wrapper | `~/.claude/bin/codex-ask` | runs codex, captures the thread id, checks for context compaction |
| rules | a block in `~/.claude/CLAUDE.md` | model and thread discipline - the main value of the package |

There is no hook any more. The old `PostToolUse` hook looked for context compaction across every
codex session on the machine and could not tell whose thread it was. The wrapper knows its own
thread id and checks only its own part of the log.

## What codex-ask does

```
codex-ask new    [--dir D] [--sandbox read-only|workspace-write|danger-full-access] [--network] [--effort E] [--model M] [--out P] PROMPT
codex-ask resume SESSION [--dir D] [--out P] PROMPT
```

1. Creates a fresh directory per call (`codex-<time>-<pid>-<random suffix>`) and prints its path
   first - even if the wrapper is killed later, the results can still be found.
2. For `resume`, takes the thread lock (`~/.cache/codex-ask/locks/<id>.lock`). If it is busy,
   exits 75 at once without starting codex. Then records where the thread log currently ends.
3. Runs `codex exec --json` (or `codex exec resume --json`) with the prompt file on stdin; events
   go to `events.jsonl`, stderr to `stderr.log`, the final answer to `answer.md`.
4. Forwards SIGTERM/SIGINT/SIGHUP to codex; if codex has not stopped within 10 seconds, sends
   SIGKILL to the whole process group. The thread lock on the codex side is released.
5. After exit, confirms from the events that the thread is the right one (exactly one UUID; on
   `resume`, equal to the requested one) and scans the thread log
   `~/.codex/sessions/.../rollout-*-<id>.jsonl` from the recorded point for compaction events.
6. Prints the summary and the answer. Exit status: codex's own; 75 - thread busy; 128+N - stopped
   by signal N; 1 - codex exited 0 but the turn did not complete or the thread was not identified.

Sample summary:

```
out_dir: /tmp/.../codex-20260923T104243-60254-f73209
session_id: 00000000-0000-0000-0000-000000000000
status: ok (exit 0)
usage: input 29211 (cached 24320), output 11, reasoning 0
compactions: none
----- answer -----
...
```

## The two rules this exists for

### 1. The model is explicit

The model is pinned in `~/.codex/config.toml` and built into the wrapper (`DEFAULT_MODEL`). The
identifier is the **slug** from `~/.codex/models_cache.json`, not the display name: "GPT-6-Astra"
is `gpt-6-astra`. On `resume` the wrapper does not pass a model: the thread stays on the one it
was created with (verified on 0.155.1 - model, sandbox and effort are preserved).

### 2. One thread per task flow

The OpenAI prompt cache matches request prefixes. Continuing a thread keeps the earlier
conversation as an identical prefix; a new thread sends the project context again. Measured
2026-04-28: two fresh threads back to back took roughly twice the inference time of one shared
thread. A cache hit is never guaranteed even on a shared thread, but there is no reason to lose it
where it can be kept.

## Sandbox (verified on 0.155.1)

- `exec` never asks for approval. Anything the sandbox does not allow is refused immediately.
  The "waiting for permission" hangs seen under MCP do not happen on the CLI.
- `read-only` (the wrapper default): agent commands cannot write anywhere, project included, and
  have no network (DNS does not resolve).
- `workspace-write --network`: writes inside the run directory and network access (`curl` gets 200).
- The codex client itself writes outside the sandbox: the session log, auth refresh and, for git
  repositories, trust entries in `~/.codex/config.toml`.

## Parallel Claude sessions (verified on 0.155.1)

- Separate threads run concurrently without conflict (verified with three).
- Two simultaneous calls on one thread are impossible: the second `codex-ask` gets 75 from the
  lock, and a bare `codex exec resume` is refused by codex with `already has an active writer`.
  The log stays intact.
- The ChatGPT plan quota and `auth.json` are shared by all sessions.

## Failure modes

| Message | What it is | What to do |
|---|---|---|
| `codex (CONNECTION_CLOSED)` at Claude Code startup | an MCP entry from the old package is still registered | remove it (`INSTALL.md`, migration) |
| `stdin is not a terminal` | a codex subcommand that does not exist (e.g. `mcp-server`) | check `codex --help` |
| `status: FAILED (exit 75)`, `BUSY` | the thread is in use by another call | wait; do not start a second one |
| `'<model>' is not supported when using Codex with a ChatGPT account` | wrong slug, or the plan's model list changed | check the slug; if still refused, use the fallback model |
| `The '<model>' model requires a newer version of Codex` | the CLI is older than the model | update codex |
| `Your access token could not be refreshed…` | auth expired | retry once, then `codex login` (from one session only) |
| `session_id: UNKNOWN`, exit 1 | the event stream did not confirm the thread | look at `events.jsonl` in `out_dir` |
| `compactions: unknown` | the thread log was not found | check `CODEX_HOME` and permissions; the thread may still be alive |
| exit 130 / 143 | the wrapper was stopped by a signal | codex is stopped, the thread is free, `resume` works |

A failed call does not by itself corrupt the thread. A new thread is needed when codex itself
says the session does not exist, when the model, directory or sandbox changes, or when after a
context compaction the thread keeps answering from lost details. The evidence must then be sent
again.

## Timeouts

The Claude Code Bash tool cuts a foreground command off after 10 minutes. Long reviews (xhigh,
big diffs) are run in the background with the wrapper's output redirected to a file, which is
read when the completion notification arrives. The `MCP_TOOL_TIMEOUT` and
`CLAUDE_CODE_MCP_TOOL_IDLE_TIMEOUT` variables from the old package have no effect on this setup.

## Deliberately not included

- **`~/.codex/auth.json`** - personal, created by `codex login`.
- **A full `~/.codex/config.toml`** - it holds personal `projects` with trust levels and paths to
  application bundles. The package ships only an example.
- **codex plugins** - unrelated to the Claude Code integration.

## Distribution archive

Built from the committed state, without working files or `.DS_Store`:

```bash
git archive --prefix=codex-cli-integration/ -o ../codex-cli-integration-$(date +%F).zip HEAD
```
