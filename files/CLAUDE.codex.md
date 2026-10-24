<!-- Managed by the codex-cli skill: installed as ~/.claude/codex-rules.md and overwritten on every update. Personal rules go to ~/.claude/CLAUDE.md, under the import line. -->

# codex (CLI through `~/.claude/bin/codex-ask`)

These rules apply in every project. `~/.codex` below means the codex directory: `CODEX_HOME` if
set, otherwise `~/.codex`. codex is called only as a CLI, there is no MCP integration. Do not
downgrade codex: older builds reject current models.

## Calls - always through the wrapper

Write the prompt to a file first.

- **New thread:** `~/.claude/bin/codex-ask new --dir <project dir> <prompt file>`.
  Defaults: `--model <MODEL>` (built into the wrapper) and `--sandbox read-only`. Options:
  `--effort xhigh` (only when the user asks), `--sandbox workspace-write` (only when codex must
  edit files and the user agreed), `--network` (only with workspace-write), `--out <dir>`.
- **Continue a thread:** `~/.claude/bin/codex-ask resume <session_id> --dir <same dir> <prompt file>`.
  Model, sandbox and effort stay as the thread was created; do not try to override them.
- The wrapper prints `out_dir` first, then the summary, then the answer. Read the summary before
  trusting the answer:
  - `session_id`, `status` - a failed call's answer is marked as possibly incomplete.
  - `BUSY` (exit 75) - another call is using the thread; see below.
  - `COMPACTED` - codex compacted its context during this call; earlier details may survive only
    in its own summary, so if the answer depends on them, send the evidence again.
    `COMPACTED (whole thread history scanned …)` - the compaction may be older than this call.
  - `compactions: unknown / not checked` - there is no reliable compaction result (the log was
    not found or not readable, the call was busy, the thread did not match); this is not "no
    compactions".
  - `warning:` / `error:` lines.
- **When something is off** - `status` not ok, `session_id: UNKNOWN`, no summary at all, auth or
  model errors that do not go away on retry, or output that makes no sense - read
  `~/.claude/codex-cli/README.md`, sections "Failure modes" and "Timeouts"; full events and stderr
  are in `out_dir`. To repair or update the setup, run `/codex-cli`.
- The Bash tool cuts a foreground command off after 10 minutes. Run long reviews (xhigh, big
  diffs) with `run_in_background: true`, redirect the wrapper's stdout to a file and read it when
  the completion notification arrives.
- Never `--ephemeral` (resume and the compaction check need the rollout) and never
  `codex exec resume --last` (it may pick someone else's session). A bare `codex exec` without the
  wrapper is only for one-off probes.

## Sandbox

- `read-only` (default): codex's commands cannot write anywhere, the project included, and have
  no network. `exec` never asks for approval: anything not allowed is refused at once.
- `workspace-write`: only when codex must edit files and the user agreed. Add `--network` only
  together with it; for network without write access to the project, set `--dir` to a temporary
  directory outside the project.

## Model - hard rule

Every new thread uses `<MODEL>` (the wrapper default), exactly that slug - no abbreviations or
variations. `<FALLBACK>` is the fallback in case of refusal, not a default.
On `'<model>' is not supported when using Codex with a ChatGPT account`: retry once on a fresh
thread; if it is refused again, use `codex-ask new --model <FALLBACK>` and tell the user that the
primary model is broken.

## One thread per task flow

Within one coherent task (reviews of one slice across several rounds; spec review and code review
of one commit; "explain -> fix -> verify" on one scope) all calls go to one thread: one
`codex-ask new`, then `codex-ask resume <session_id>`. A continued thread keeps the context and
the chance of a prompt-cache hit; a new one pays for the project context again.

## When to start a new thread

A failed call does not by itself corrupt the thread. Decide by cause:

- `BUSY`: another process is using the thread. Wait for it (check your own background tasks
  first); do not start a second writer.
- Auth, network, rate-limit or timeout errors: fix the cause and `resume` the same thread; check
  that the answer covers the whole question. Before retrying after a timeout or a kill, make sure
  the previous run has ended (no `BUSY`); for a writable sandbox, first look at what it already
  changed.
- codex itself reports the session cannot be found: new thread, send the needed evidence again.
- On purpose: when the model, directory or sandbox must change, the topic shifts radically, or
  after `COMPACTED` the thread keeps answering from lost details. An empty new thread does not
  bring the evidence back - attach it.

## Parallel Claude sessions

Separate threads run in parallel without conflict. All sessions share one ChatGPT plan quota and
one `~/.codex/auth.json`: on a rate limit, pause and retry later instead of hammering. On
`Your access token could not be refreshed…`, retry once; if it persists, ask the user to run
`! codex login` once - not from several sessions.

## Reasoning effort

The default is `high` from `~/.codex/config.toml`. `--effort xhigh` only when the user explicitly
asks for it for a specific review. Effort is set when the thread is created and is not changed on
resume.
