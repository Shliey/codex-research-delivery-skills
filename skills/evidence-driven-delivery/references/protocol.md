# Controller protocol

All helper writes are project-local. Commands return JSON. Put keyword arguments
in a JSON file and pass `--input`; never interpolate user strings into shells.
The Agent calls these helpers; the human only supplies goals/decisions.

## Entry and state

`start`: `goal`, `scope`, `mode` (`full`/`light`), optional `issue`, `change`,
`authorization: {source, scope, actions: ["implement"]}`. Source is a real host
message reference. Planning-only requests never populate implementation grants.
`review_only: true` returns OBSERVATIONAL without writes or initialization.
Use `status --run ID` and inspect real artifacts before `resume`. The helper
refuses implicit legacy migration. Terminal runs remain immutable; a new goal
starts a new run.

`step`: `{"result":{"status":"completed","readiness":"READY","event":"ISSUE_READY"}}`.
Events are enumerated by state in `assets/workflow.json`; common non-success
events are WAIT, ERROR, PAUSE, CANCEL and NEEDS_DECISION. Use `request_decision`
instead of emitting a naked NEEDS_DECISION event. Suspended runs retain their
explicit resume state; `resume` cannot approve a pending decision.

`bind`: `contract`, optional `issue`/`change`. Contract is:
```json
{
  "tasks": {"T1": {"writes": ["src/config.py", "tests/test_config.py"], "depends": []}},
  "scenarios": [{
    "id": "S1", "requirement": "Reject invalid configuration",
    "source": "openspec/changes/reject-invalid/specs/config/spec.md",
    "heading": "#### Scenario: Invalid configuration",
    "tasks": ["T1"], "checks": ["test"]
  }]
}
```
Use stable IDs and include EVERY in-scope scenario. The semantic reviewer must
compare the map against the entire issue/spec, not just the listed rows. Each
task has non-overlapping write ownership or an explicit serial merge owner.
Shared contracts precede dependent tasks. v1 executes serially; it may describe
parallel lanes but does not spawn agents or pretend they ran independently.

`review`: `kind` (design/planning/semantic), `findings` (blocking findings array),
`source` (review record or host analysis reference). Record only after doing the
review, and after edits are final. Fresh design review gates READY; fresh
planning review and contract gate DELIVERY_READY. Final semantic review inspects
the actual diff for non-goals, design deviations and uncovered scenarios.

## Decisions and authorization

`request_decision`: `question`, `action`, `paths`, `options`, `recommendation`.
Include all approval-relevant files and scope/policy inputs. It saves the return
state and baseline. `decide`: `decision_id`, `answer`, `source`, `approved`.
Only call after the actual human answer. It resumes immediately; no second
"continue" command. Changed inputs invalidate the packet: resume to the saved
state by replacing the stale packet, ask the updated question and record it.
Use `replace_decision` with `decision_id` to supersede an unanswered packet;
then create the replacement. This never records an approval.
No routine document approval is required within an existing implementation grant.

## Operations, recovery, checks

`begin`: `operation` (stable unique logical ID), `outputs` (exact file paths,
including paths expected to disappear), `action` (default local_edit).
If replay=false, do not repeat the effect. Inspect outputs and use `reconcile`:
`operation`, `expected` mapping each exact path to SHA256 bytes or `MISSING`.
This verifies postconditions, but the Agent must also inspect semantics.
`complete`: `operation` records successful postconditions after actual work.
Never record successful receipt before checking outputs. Never blindly repeat
a partially completed write: repair partial state within scope first.

`check`: `name` from project commands. Records actual argv, cwd, exit code,
timestamp, log and baseline. Runs with no shell and a timeout. `evidence_status`
requires configured checks, all mapped checks, current log bytes, scenario
sources and a fresh semantic review. Source/policy/config changes invalidate
evidence. If formatting or task marking changes fingerprinted input, rerun checks
and review. Generated outputs must be explicitly ignored in project config.

`finish_task`: `task` ID; requires completed dependencies and fresh executed
scenario checks. Record after final code/task edits. A later source change
invalidates completion evidence conservatively; rerun checks and re-confirm
affected task outcomes rather than trusting old checkboxes.

Use event details as a stable failure signature (tool + test/error identity),
not timestamps or changing stack traces. Three repair attempts are allowed;
the next repeated failure enters PAUSED. Preserve diagnosis and request human
action only if a real decision/external prerequisite remains. Budget exhaustion
does not authorize unlimited resume loops.

State replacement is atomic under an exclusive run lock. A pending operation
prevents a second operation writer. After an interrupted projection write,
`resume` regenerates events/evidence/handoff from authoritative state. A stale
writer.lock is never auto-deleted: inspect its PID and in-flight effects, verify
the prior writer exited, then remove that exact lock and reconcile. Host tool
permissions are the real security boundary; JSON provenance cannot authenticate
a human or protect against a malicious local process.

## Closure

After fresh VERIFIED, local full delivery emits LOCAL_COMPLETE; local light
delivery emits LIGHT_COMPLETE and ends COMPLETED. Nonlocal endpoints require
specific authorization, real operation `delivered`, and `post_verified` checks.
Do not confuse approval with performing delivery.

For full mode: begin operation `synced`, apply delta specs using schema-provided
rules, verify exact merged behavior and complete receipt, emit SYNCED. Then begin
`archived`, archive with validation and no bypass flags, inspect the archive
target and complete receipt, emit ARCHIVED. CLI archive may perform sync itself:
reconcile already merged specs, avoid double application. On crash after moving,
locate and verify the canonical archived change instead of creating a duplicate.
Archival changes paths/baseline; record closure receipts separately from pre-move
test evidence. No requirement to rerun business tests merely because the archive
directory moved. Never archive an incomplete change by suppressing warnings.
