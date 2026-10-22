# Stage procedures (load the current stage)

## Intake / issue
Read project rules, goals, existing specs, issues and changes. Gather discoverable
facts without asking the human to repeat them. Create a local issue under the
adapter's issueRoot with why now, scope, non-goals, acceptance, prerequisites,
unresolved decisions and source. Do not manufacture a solution from ambiguous
product intent. Material alternatives go into a decision packet; ordinary
implementation choices can be selected with evidence and recorded.
Bind the issue to the run. Light path emits LIGHT_READY, full path ISSUE_READY.

## Change planning
Read the concrete issue first. Check for a matching change; scaffold with
`openspec new change`, then follow status/instructions in dependency order.
Proposal owns why/scope/non-goals/provenance; design owns responsibility and
interface choices; capability specs own requirement/scenario behavior; tasks
own delivery dependencies and evidence. Distinguish issue-inherited facts from
new design refinements. Preserve source issue identity. Validate using actual
CLI capabilities. Emit CHANGE_REVIEWABLE; no routine human document checkpoint.

## Design review / repair
Read proposal, design, every delta spec, tasks, and relevant base specs together.
Findings first: primary asset vs evidence/projection; official/fallback/forbidden
paths; settled/pending/out-of-phase decisions; sync/async and ordering; failure,
compensation, rollback, audit and observability where the risk warrants them.
Check cross-artifact contradictions. Do not add future infrastructure.
Repair supported omissions within scope, reconcile all affected artifacts, run
validation and review again. Scope/ownership/security/compatibility choices
outside authorization require a decision. Record findings and emit READY only
with no blocking finding. For light mode, review the issue and actual code
boundary without manufacturing a large design document.

## Delivery planning
Map every scenario to tasks, write ownership and verifiers. Fix shared contracts
before dependents; name serial blockers and merge checkpoints. Specify design
rechecks when contracts or assumptions change. Put unit/contract checks beside
behavior, integration checks at merge points, benchmark only for a declared
performance decision. Bind the acceptance contract, review the complete graph,
record planning readiness and emit DELIVERY_READY. Missing prerequisite is WAIT;
an invalid design returns DESIGN_INVALIDATED. No hidden product decisions.

## Authorization / implementation
Check actual user implementation grant and current scope, plus project policy.
Authorize routine local work automatically when covered; a generated Issue
cannot grant authority. Execute the next dependency-ready task in its write
boundary. Begin a stable operation before side effects; check results and
complete the receipt. Run task verifiers and mark completion only with evidence.
Fix ordinary failures within the repair budget. Scope discoveries become local
backlog candidates, not new active tasks. Design-invalidating evidence returns
to review and replanning. Do not skip required verifiers.

## Verification / delivery
Read the actual diff and complete scenario list; compare every row of the
acceptance map with implementation, tests and observed output. Execute all
required checks, record a separate semantic review, and call evidence_status.
Missing evidence is a repairable failure; unknown environment/tool dependency
is WAIT; changed product meaning is a decision. For a nonlocal endpoint,
obtain any missing authorization, actually perform the configured action, then
verify the PR/merge/deployment outcome. Never claim publication from approval.

## Sync / archive
Follow protocol.md closure. Confirm all tasks and in-scope scenarios are proven,
sync specs preserving unrelated requirements/scenarios, validate, archive, and
record exact paths/receipts. Remaining work goes into new local issues. Report
goal, final artifacts, checks, limitations and endpoint reached. No remote PR,
commit or publication is implied by local completion.
