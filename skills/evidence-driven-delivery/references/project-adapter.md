# Target adoption

Run `python <skill>/scripts/delivery.py <target> scan` (read-only). It detects
package scripts, Python unittest discovery and OpenSpec CLI availability/version.
It does not install dependencies or assume discovered scripts are safe. Inspect
CI, manifests, nested instructions, and actual test framework; adapt the result
before executing commands. For pytest/uv/Poetry, Rust, monorepos, Windows launchers
or custom tools, supply their actual argv and cwd through project configuration.

Run `init` for an authorized onboarding/delivery request. It creates missing
`.workflow/{workflow,policy,project,skill-result.schema,run-state.schema}.json`
and appends one marked AGENTS entry. Repeating init preserves custom values and
existing rules. `doctor` reports invalid references/configuration, missing
executables, and legacy runs. No tests discovered is a warning during adoption
and a blocker for delivery. Do not silently fall back to successful no-op tests.

## Adapter example

```json
{
  "version": 2,
  "stacks": ["python"],
  "commands": {
    "test": {"argv": ["python", "-m", "pytest"], "required": true, "timeout": 120}
  },
  "issueRoot": ".workflow/issues",
  "endpoint": "local",
  "deliveryCommands": {},
  "openspec": {"available": true, "root": "openspec", "store": null},
  "ignore": [".git", ".workflow", ".venv", "__pycache__", ".pytest_cache"]
}
```

`commands` contains shell-free argv arrays, timeout in seconds, optional
project-relative `cwd`, and whether a command is required. Inspect commands for
external effects before running them. Secrets stay in the host credential
mechanism, never config or evidence logs. Ignore only regenerated outputs, not
source/tests/specs. Command and policy changes invalidate existing evidence.

`endpoint` is local (default), pr, merge, or deploy. Nonlocal endpoints need a
trusted explicit grant for that exact endpoint and actual execution/verification
receipts. Record the corresponding action and command in `deliveryCommands`;
the helper never executes publication implicitly. Commit/push is not implied by
local delivery. Light mode is local only; nonlocal tasks use full mode.

When Python unittest discovery does not match the target's framework, replace
the discovered candidate with the actual CI command. Package script discovery
is a candidate list, not evidence that every script is non-mutating. Formatter
commands that modify source cannot serve as read-only final verification.

Full mode requires OpenSpec. Probe version/help and initialize only when needed
and authorized. Use `openspec status/instructions` paths and schemas, not guessed
locations. A selected store is sticky on every store-aware command; observe
host permission constraints for paths outside the target. If unavailable,
checkpoint WAITING_DEPENDENCY with the installation requirement. Do not label an
unarchived full delivery complete or install network dependencies silently.

## Upgrade

Existing project values win over discovered defaults. V1 YAML and legacy runs
must be retained and explicitly reviewed/mapped to v2; never pretend an old
approval satisfies the new scope/baseline contract. In a pre-v2 repository,
replace the obsolete AGENTS routing section as a reviewable edit while preserving
unrelated project rules. The managed entry alone does not override conflicting
existing instructions.

To reuse: copy this entire skill folder into the target's `.agents/skills/`
(or install into a host-supported personal skill directory), then invoke it
with the target goal. No source repository files or sibling skills are needed.
