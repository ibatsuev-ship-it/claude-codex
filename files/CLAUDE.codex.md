<!-- ================= codex CLI - block for ~/.claude/CLAUDE.md ================= -->
<!-- BEFORE INSERTING fill in the placeholders:                                    -->
<!--   <MODEL>    - the slug confirmed by `codex exec --skip-git-repo-check ...`   -->
<!--   <FALLBACK> - the fallback slug                                              -->
<!-- Verified 2026-09-23: <MODEL> = gpt-6-astra, <FALLBACK> = gpt-5.6-sol         -->
<!-- If the fallback itself became the primary, delete EVERY mention of <FALLBACK>: -->
<!-- the note in the list of forbidden values and the paragraph about switching   -->
<!-- to the fallback. There are two.                                              -->

## codex (CLI through `~/.claude/bin/codex-ask`)

These rules apply in every project. `~/.codex` below means the codex directory: `CODEX_HOME` if
set, otherwise `~/.codex`.

codex is called only as a CLI (codex-cli 0.155.1, `@openai/codex` via npm); there is no MCP integration. **Do not downgrade codex** - older builds reject current models. `codex app-server` is a JSON-RPC daemon with its own protocol and is not used.

### Calls - always through the wrapper

`~/.claude/bin/codex-ask` (Python, standard library only) wraps `codex exec --json`: it takes the
session id from the `thread.started` event, writes events, stderr and the final answer into a fresh
directory per call, checks its own part of the thread's rollout file for context compaction after
the run, and prints `out_dir` first, then the summary and the answer.
Exit status: codex's own; 75 - thread busy; 128+N - stopped by signal N (the wrapper forwards
SIGTERM/SIGINT/SIGHUP to codex, so the thread lock is released); 1 - codex exited 0 but the turn
did not complete or the event stream did not confirm the requested thread (then
`session_id: UNKNOWN`). `codex-ask` calls on one thread are serialized by a lock in
`~/.cache/codex-ask/locks/`. Write the prompt to a file first.

- **New thread:** `~/.claude/bin/codex-ask new --dir <project dir> <prompt file>`.
  Defaults: `--model <MODEL>` (built into the wrapper) and `--sandbox read-only`. Options:
  `--effort xhigh` (only when the user asks), `--sandbox workspace-write` (only when codex must
  edit files and the user agreed), `--network` (only with workspace-write), `--out <dir>`.
- **Continue a thread:** `~/.claude/bin/codex-ask resume <session_id> --dir <same dir> <prompt file>`.
  The wrapper passes neither `--model` nor `-c` on resume: the CLI would accept an override, but
  model, sandbox and effort must stay as the thread was created.
- Summary: `session_id`, `status`, `COMPACTED` (codex compacted its context during this call -
  earlier details may survive only in its own summary; if the answer depends on them, send the
  evidence again), `COMPACTED (whole thread history scanned …)` (the rollout could not be bounded
  to this call, so the events may be older), `compactions: unknown / not checked` (the rollout was
  not found, the call was busy or the thread id did not match - not the same as "no compactions"),
  `BUSY`, `warning:` / `error:` lines, then the answer.
  The answer of a failed call is marked as possibly incomplete. Full events and stderr are in `out_dir`.
- The Claude Code Bash tool cuts a foreground command off after 10 minutes. Run long reviews
  (xhigh, big diffs) with `run_in_background: true`, redirect the wrapper's stdout to a file and
  read it when the completion notification arrives. If the wrapper was killed with SIGKILL there
  is no summary - look in `out_dir` (printed first).
- Never `--ephemeral` (without a rollout neither resume nor the compaction check works) and never
  `codex exec resume --last` (it takes the newest session for the directory, which may belong to
  someone else).
- Profiles: in 0.155.1 `-p NAME` layers the file `$CODEX_HOME/NAME.config.toml`; the old
  `[profiles.*]` tables in `config.toml` are not what `-p` loads. The wrapper uses no profile.
- A bare `codex exec` without the wrapper works but loses the session id and the compaction check -
  only for one-off probes.

### Sandbox (verified on 0.155.1)

- The sandbox restricts the commands codex's agent runs. The codex client itself still writes the
  rollout, refreshes auth and, for git repositories, adds trust entries to `~/.codex/config.toml`.
- `read-only`: agent commands cannot write anywhere, project included, and have no network. `exec`
  never asks for approval, so an escalation is refused at once, nothing hangs, and
  `danger-full-access` is not needed.
- `workspace-write` + `--network`: writes inside the run directory (plus temp and any configured
  writable roots) and network. For network without write access to the project, run with `--dir`
  set to a temporary directory outside the project.

### Model - hard rule

Every new thread uses `<MODEL>` (the wrapper default). Other values only under the fallback rule
below.

- No abbreviations or variations (`astra`, `gpt-6`, `gpt-6-astra-codex`, `gpt-5.6`, `gpt-5.6-codex`, `gpt-5-codex`).
  `<FALLBACK>` is the fallback in case of refusal, not a default.
- The account is a ChatGPT plan. The slug comes from `~/.codex/models_cache.json` (field `slug`);
  the display name is not an identifier.
- `~/.codex/config.toml` also pins `model = "<MODEL>"`.
- On `'<model>' is not supported when using Codex with a ChatGPT account`: retry once on a fresh
  thread; if it is refused again, use `codex-ask new --model <FALLBACK>` and tell the user that the
  primary model is broken.

### One thread per task flow

Within one coherent task (reviews of one slice across several rounds; spec review and code review
of one commit; "explain -> fix -> verify" on one scope) all calls go to one thread: one
`codex-ask new`, then `codex-ask resume <session_id>`.

Why: the OpenAI prompt cache matches request prefixes. Continuing a thread keeps the earlier
conversation as an identical prefix, which is likely to hit the cache; a new thread sends the
project context again and usually pays for it again. Measured 2026-04-28: two fresh threads back
to back took roughly twice the inference time of one shared thread. A hit is never guaranteed
(the cache expires, and changed context breaks the prefix).

### When to start a new thread

A failed call does not by itself corrupt the thread: the rollout is persisted and the writer lock
keeps calls from interleaving. Decide by cause:

- `BUSY` (exit 75): another process is using the thread. Wait for it (check your own background
  tasks first); do not start a second writer.
- Auth, network, rate-limit or timeout errors: fix the cause and `resume` the same thread; check
  that the answer covers the whole question. Before retrying after a timeout or a kill, make sure
  the previous run has ended (no `BUSY`); for a writable sandbox, first look at what it already changed.
- codex itself reports the session cannot be found: new thread, send the needed evidence again.
  `compactions: unknown` alone does not mean the thread is gone (check `CODEX_HOME` and permissions).
- A new thread on purpose: when the model, directory or sandbox must change, the topic shifts
  radically, or after `COMPACTED` the thread keeps answering from lost details. Attach the
  evidence in the new thread: an empty new thread does not bring it back.

### Parallel Claude sessions

- Separate threads run in parallel without conflict. Concurrent writes to one thread are refused
  (`already has an active writer`, exit 75); the rollout stays intact.
- All sessions share one ChatGPT plan quota and one `~/.codex/auth.json`. On a rate limit, pause
  and retry later instead of hammering. On `Your access token could not be refreshed…`, retry
  once; if it persists, ask the user to run `! codex login` once. Do not run logins from several
  sessions and do not abandon threads over it.

### Reasoning effort

The default is `high` from `~/.codex/config.toml`. `--effort xhigh` only when the user explicitly
asks for it for a specific review. Effort is set when the thread is created and, by wrapper
policy, is not changed on resume.

### Error messages

- `stdin is not a terminal` - a codex subcommand that does not exist fell through to the
  interactive TUI. See `codex --help`.
- `'<model>' is not supported when using Codex with a ChatGPT account` - wrong slug, or the plan's
  model list changed; see the model rule.
- `The '<model>' model requires a newer version of Codex` - the installed CLI is too old for the
  model. Update codex.
- `Your access token could not be refreshed…` - see "Parallel Claude sessions".
- `already has an active writer` - see `BUSY`.
<!-- ============================ end of codex block ============================ -->
