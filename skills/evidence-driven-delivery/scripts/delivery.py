"""Synchronous Agent workflow helpers, Python 3.11+ standard library.

Semantic decisions belong to the host Agent. This is not a background runner.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid
import zipfile

ASSETS = Path(__file__).resolve().parent.parent / "assets"
SUSPENDED = {"AWAITING_DECISION", "WAITING_DEPENDENCY", "ERROR", "PAUSED"}
ENTRY = """<!-- evidence-driven-delivery:start -->
## Delivery workflow
For outcome-level implementation requests, use the installed
`evidence-driven-delivery` skill. Inspect/resume project-local `.workflow/`
state and follow existing project rules and user authorization. Route routine
steps automatically; reviews remain observational. Ask only for decisions or
actions outside the existing authorization.
<!-- evidence-driven-delivery:end -->
"""


def now():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def safe(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Path escapes project: " + str(relative))
    return path


def validate(value, schema):
    """Validate the JSON-schema vocabulary used by the shipped contracts."""
    types = {"object": dict, "array": list, "string": str, "integer": int, "boolean": bool, "null": type(None)}
    if "type" in schema:
        names = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(isinstance(value, types[n]) and not (n == "integer" and isinstance(value, bool)) for n in names):
            raise ValueError("Schema type mismatch")
    if "const" in schema and value != schema["const"]:
        raise ValueError("Schema constant mismatch")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError("Schema enum mismatch")
    if isinstance(value, dict):
        if not set(schema.get("required", [])).issubset(value):
            raise ValueError("Missing required schema fields")
        props = schema.get("properties", {})
        if schema.get("additionalProperties") is False and not set(value).issubset(props):
            raise ValueError("Unknown schema fields")
        for key in value.keys() & props.keys():
            validate(value[key], props[key])
    if isinstance(value, list) and "items" in schema:
        for item in value:
            validate(item, schema["items"])
    if isinstance(value, str) and len(value) < schema.get("minLength", 0):
        raise ValueError("String is too short")
    if isinstance(value, int) and value < schema.get("minimum", value):
        raise ValueError("Number below minimum")


def package_skill(output):
    """Export only this skill, excluding caches and target project state."""
    output = Path(output).resolve()
    source = ASSETS.parent
    if output.is_relative_to(source):
        raise ValueError("Package output must be outside the skill folder")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(source.rglob("*")):
            if file.is_file() and "__pycache__" not in file.parts and file.suffix != ".pyc":
                archive.write(file, "evidence-driven-delivery/" + file.relative_to(source).as_posix())
    return {"path": str(output), "sha256": hashlib.sha256(output.read_bytes()).hexdigest()}


def argv_run(argv, root, timeout=120):
    executable = shutil.which(argv[0])
    if not executable:
        return {"argv": argv, "exitCode": 127, "output": "Executable not found: " + argv[0]}
    try:
        proc = subprocess.run([executable, *argv[1:]], cwd=root, capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=timeout)
        return {"argv": argv, "exitCode": proc.returncode, "output": proc.stdout + proc.stderr}
    except subprocess.TimeoutExpired:
        return {"argv": argv, "exitCode": 124, "output": "Command timed out"}


def scan(root):
    root = Path(root).resolve()
    commands, stacks = {}, []
    if (root / "package.json").exists():
        pkg = read(root / "package.json")
        stacks.append("typescript" if (root / "tsconfig.json").exists() else "javascript")
        manager = "pnpm" if (root / "pnpm-lock.yaml").exists() else "yarn" if (root / "yarn.lock").exists() else "npm"
        for name in ("test", "check", "lint", "typecheck", "build"):
            if name in pkg.get("scripts", {}):
                commands[name] = {"argv": [manager, "run", name], "required": True, "timeout": 120}
    if (root / "pyproject.toml").exists() or list(root.glob("*.py")):
        stacks.append("python")
        if (root / "tests").is_dir():
            commands["python-test"] = {"argv": [sys.executable, "-m", "unittest", "discover", "-s", "tests"], "required": True, "timeout": 120}
    openspec = argv_run(["openspec", "--version"], root, 15)
    return {"version": 2, "stacks": stacks, "commands": commands,
            "issueRoot": ".workflow/issues", "endpoint": "local", "deliveryCommands": {},
            "openspec": {"available": openspec["exitCode"] == 0,
                         "version": openspec["output"].strip(), "root": "openspec", "store": None},
            "ignore": [".git", ".workflow", "node_modules", ".venv", "__pycache__", ".pytest_cache", "dist", "coverage"]}


class Controller:
    def __init__(self, root, run=None):
        self.root = Path(root).resolve()
        self.control = self.root / ".workflow"
        self.run = run
        if run is not None and not re.fullmatch(r"[a-zA-Z0-9_-]+", run):
            raise ValueError("Invalid run ID")

    @property
    def folder(self):
        if not self.run:
            raise ValueError("A run ID is required")
        return self.control / "runs" / self.run

    def project(self):
        return read(self.control / "project.json")

    def workflow(self):
        return read(self.control / "workflow.json")

    def policy(self):
        return read(self.control / "policy.json")

    def init(self):
        self.control.mkdir(exist_ok=True)
        for name in ("workflow.json", "policy.json", "skill-result.schema.json", "run-state.schema.json"):
            target = self.control / name
            if not target.exists():
                write(target, read(ASSETS / name))
        if not (self.control / "project.json").exists():
            write(self.control / "project.json", scan(self.root))
        target = self.root / "AGENTS.md"
        text = target.read_text(encoding="utf-8") if target.exists() else ""
        if "<!-- evidence-driven-delivery:start -->" not in text:
            target.write_text(text.rstrip() + "\n\n" + ENTRY, encoding="utf-8")
        return self.doctor()

    def doctor(self):
        errors, warnings = [], []
        try:
            wf, project = self.workflow(), self.project()
            if wf.get("version") != 2 or project.get("version") != 2 or self.policy().get("version") != 2:
                errors.append("Unsupported control contract version")
            if not isinstance(self.policy()["maxRepairAttempts"], int) or not 1 <= self.policy()["maxRepairAttempts"] <= 3:
                errors.append("Repair budget must be between one and three attempts")
            targets = set(wf["states"]) | set(wf["terminalStates"])
            for state, node in wf["states"].items():
                for event, target in {**wf["commonEvents"], **node["events"]}.items():
                    if target not in targets:
                        errors.append(f"Undefined target {state}/{event}/{target}")
            if not project["commands"]:
                warnings.append("No validation commands discovered; configure before delivery")
            for name, cmd in project["commands"].items():
                if not cmd.get("argv") or not isinstance(cmd["argv"], list):
                    errors.append("Invalid command: " + name)
                elif not shutil.which(cmd["argv"][0]):
                    errors.append("Missing executable: " + cmd["argv"][0])
            if project["endpoint"] not in {"local", "pr", "merge", "deploy"}:
                errors.append("Unknown delivery endpoint")
            for legacy in (self.control / "runs").glob("*/state.json"):
                if read(legacy).get("version") != 2:
                    warnings.append("Legacy run retained; explicit migration required: " + legacy.parent.name)
            read(self.control / "skill-result.schema.json")
            read(self.control / "run-state.schema.json")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append(str(exc))
        return {"ok": not errors, "errors": errors, "warnings": warnings}

    def snapshot(self, paths=None):
        project = self.project()
        if paths is not None:
            files = [safe(self.root, p) for p in paths]
        else:
            files = []
            for base, dirs, names in os.walk(self.root, followlinks=False):
                dirs[:] = sorted(d for d in dirs if d not in project["ignore"] and not (Path(base) / d).is_symlink())
                files.extend(Path(base) / name for name in sorted(names))
        entries = []
        for p in sorted(files):
            if p.is_symlink():
                raise ValueError("Evidence cannot traverse symlink: " + str(p))
            entries.append([p.relative_to(self.root).as_posix(), hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else "MISSING"])
        # Policy and command changes invalidate evidence even though run state is excluded.
        if paths is None:
            entries.extend([["@project", digest(project)], ["@policy", digest(self.policy())]])
        return digest(entries)

    def baseline(self, state):
        # Local issues live in ignored runtime storage but still affect scope.
        issue = state.get("issue")
        issue_digest = self.snapshot([issue]) if issue and not str(issue).startswith(("https:", "http:")) else issue
        return digest([self.snapshot(), state["scope"], state.get("contract"), issue_digest])

    @contextmanager
    def locked(self):
        self.folder.mkdir(parents=True, exist_ok=True)
        lock = self.folder / "writer.lock"
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise ValueError("Run has another writer; inspect lock owner before recovery") from None
        try:
            os.write(fd, json.dumps({"pid": os.getpid(), "at": now()}).encode())
            os.close(fd)
            yield
        finally:
            lock.unlink(missing_ok=True)

    def load(self):
        state = read(self.folder / "state.json")
        if state.get("version") != 2:
            raise ValueError("Legacy state needs explicit migration")
        return state

    def save(self, state, event):
        current = self.folder / "state.json"
        if current.exists() and read(current)["state"] in self.workflow()["terminalStates"]:
            raise ValueError("Terminal run is immutable")
        validate(state, read(self.control / "run-state.schema.json"))
        state["revision"] += 1
        state["history"].append({"revision": state["revision"], "event": event, "state": state["state"], "at": now()})
        write(self.folder / "state.json", state)
        # Rebuild projections from authoritative state after an interrupted save.
        (self.folder / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in state["history"]), encoding="utf-8")
        write(self.folder / "evidence.json", state["evidence"])
        (self.folder / "decisions.md").write_text(json.dumps(state["decisions"], indent=2), encoding="utf-8")
        (self.folder / "handoff.md").write_text(
            f"Run: {state['id']}\nState: {state['state']}\nResume: {state['resumeState']}\n"
            f"Diagnostic: {state.get('diagnostic', '')}\nNext: inspect state and postconditions, dispatch current action.\n", encoding="utf-8")

    def start(self, goal, scope="", mode="full", issue=None, change=None, authorization=None, review_only=False):
        if review_only:
            return {"state": "OBSERVATIONAL", "action": "review", "mutations": []}
        if not goal.strip() or mode not in {"light", "full"}:
            raise ValueError("Need a goal and light/full mode")
        candidates = []
        for file in sorted((self.control / "runs").glob("*/state.json")):
            existing = read(file)
            if existing.get("version") != 2:
                continue
            matches = ((change and existing.get("change") == change) or (issue and existing.get("issue") == issue) or existing["goal"] == goal)
            if matches and existing["state"] not in self.workflow()["terminalStates"]:
                candidates.append(existing)
        if len(candidates) > 1:
            raise ValueError("Multiple matching runs; resolve identity before resuming")
        if candidates:
            self.run = candidates[0]["id"]
            return candidates[0]
        self.run = "run-" + uuid.uuid4().hex[:12]
        grant = dict(authorization or {})
        if grant:
            grant["policyDigest"] = digest(self.policy())
        state = {"version": 2, "id": self.run, "state": "DESIGN_REVIEW" if change else "CHANGE_PLANNING" if issue else "INTAKE",
                 "resumeState": None, "revision": 0, "goal": goal, "scope": scope, "mode": mode,
                 "issue": issue, "change": change, "authorization": grant, "decisions": [],
                 "operations": {}, "failures": {}, "evidence": [], "history": [], "contract": None, "reviews": {}, "completedTasks": {}}
        with self.locked():
            self.save(state, "START")
        return state

    def bind(self, contract, issue=None, change=None):
        if not contract.get("scenarios") or not contract.get("tasks"):
            raise ValueError("Contract needs scenarios and tasks")
        tasks = contract["tasks"]
        if len({s["id"] for s in contract["scenarios"]}) != len(contract["scenarios"]):
            raise ValueError("Duplicate scenario ID")
        for task, spec in tasks.items():
            if not spec.get("writes") or not set(spec.get("depends", [])).issubset(tasks):
                raise ValueError("Task lacks writes or has unknown dependencies: " + task)
        def visit(task, seen):
            if task in seen:
                raise ValueError("Cyclic task dependency")
            for dep in tasks[task].get("depends", []):
                visit(dep, seen | {task})
        for task in tasks:
            visit(task, set())
        checks = self.project()["commands"]
        for row in contract["scenarios"]:
            if not row.get("requirement") or not row.get("heading"):
                raise ValueError("Scenario needs requirement and source heading")
            if not row.get("tasks") or not set(row["tasks"]).issubset(tasks):
                raise ValueError("Scenario has no known task")
            if not row.get("checks") or not set(row["checks"]).issubset(checks):
                raise ValueError("Scenario needs configured checks")
            safe(self.root, row["source"])
        with self.locked():
            s = self.load()
            s["contract"] = contract
            if issue is not None:
                s["issue"] = issue
            if change is not None:
                s["change"] = change
            self.save(s, "CONTRACT_BOUND")
        return s

    def request_decision(self, question, action, paths, options, recommendation=""):
        with self.locked():
            s = self.load()
            if s["state"] in SUSPENDED:
                raise ValueError("Resolve existing suspension first")
            d = {"id": "decision-" + uuid.uuid4().hex[:10], "question": question,
                 "action": action, "paths": paths, "options": options, "recommendation": recommendation,
                 "scope": s["scope"], "baseline": self.snapshot(paths),
                 "policyDigest": digest(self.policy()), "state": "pending", "source": None}
            s["decisions"].append(d)
            s["resumeState"], s["state"] = s["state"], "AWAITING_DECISION"
            self.save(s, "NEEDS_DECISION")
        return d

    def decide(self, decision_id, answer, source, approved=True):
        if not source or not answer:
            raise ValueError("Human answer and trusted message reference required")
        with self.locked():
            s = self.load()
            d = next(d for d in s["decisions"] if d["id"] == decision_id)
            if d["state"] != "pending" or s["state"] != "AWAITING_DECISION":
                raise ValueError("Decision is not pending")
            if d["scope"] != s["scope"] or d["baseline"] != self.snapshot(d["paths"]) or d["policyDigest"] != digest(self.policy()):
                raise ValueError("Decision baseline changed; replace the decision packet")
            d.update(state="approved" if approved else "rejected", source=source, answer=answer)
            s["state"] = s["resumeState"] if approved else "REJECTED"
            s["resumeState"] = None
            self.save(s, "DECISION_RECORDED")
        return s

    def authorized(self, s, action):
        grant = s["authorization"]
        if action == "implement" and grant.get("source") and grant.get("scope") == s["scope"] and action in grant.get("actions", []) and grant.get("policyDigest") == digest(self.policy()):
            return True
        return any(d["state"] == "approved" and d["action"] == action and d["scope"] == s["scope"]
                   and d["baseline"] == self.snapshot(d["paths"]) and d["policyDigest"] == digest(self.policy()) for d in s["decisions"])

    def review(self, kind, findings, source):
        if kind not in {"design", "planning", "semantic"} or not source:
            raise ValueError("Review kind/source required")
        with self.locked():
            s = self.load()
            s["reviews"][kind] = {"baseline": self.baseline(s), "findings": findings, "source": source, "at": now()}
            self.save(s, "REVIEW_RECORDED")
        return s["reviews"][kind]

    def fresh_review(self, s, kind):
        r = s["reviews"].get(kind, {})
        return r.get("baseline") == self.baseline(s) and not r.get("findings", ["missing review"])

    def evidence_status(self, s=None):
        s = s or self.load()
        baseline = self.baseline(s)
        passed = {e["name"] for e in s["evidence"] if e["baseline"] == baseline and e["exitCode"] == 0
                  and safe(self.root, e["log"]).is_file() and self.snapshot([e["log"]]) == e["logDigest"]}
        required = {n for n, c in self.project()["commands"].items() if c.get("required", True)}
        gaps = []
        if not required:
            gaps.append("No required verifier configured")
        if not required.issubset(passed):
            gaps.append("Missing fresh checks: " + ", ".join(sorted(required - passed)))
        if not s.get("contract"):
            gaps.append("Missing acceptance contract")
        else:
            for task in s["contract"]["tasks"]:
                receipt = s.get("completedTasks", {}).get(task)
                if not receipt or receipt["baseline"] != baseline:
                    gaps.append("Task lacks current completion evidence: " + task)
            for row in s["contract"]["scenarios"]:
                p = safe(self.root, row["source"])
                if not p.is_file() or row["heading"] not in p.read_text(encoding="utf-8"):
                    gaps.append("Missing scenario source: " + row["id"])
                if not set(row["checks"]).issubset(passed):
                    gaps.append("Scenario lacks fresh evidence: " + row["id"])
        if not self.fresh_review(s, "semantic"):
            gaps.append("Missing fresh semantic review")
        return {"ok": not gaps, "gaps": gaps, "baseline": baseline, "passed": sorted(passed)}

    def finish_task(self, task):
        with self.locked():
            s = self.load()
            if not s.get("contract") or task not in s["contract"]["tasks"]:
                raise ValueError("Unknown task")
            task_spec = s["contract"]["tasks"][task]
            if not all(s.get("completedTasks", {}).get(dep, {}).get("baseline") == self.baseline(s) for dep in task_spec.get("depends", [])):
                raise ValueError("Task dependencies are incomplete")
            required = {check for row in s["contract"]["scenarios"] if task in row["tasks"] for check in row["checks"]}
            valid = set(self.evidence_status(s)["passed"])
            if not required or not required.issubset(valid):
                raise ValueError("Task needs fresh executed check evidence")
            s.setdefault("completedTasks", {})[task] = {"baseline": self.baseline(s), "checks": sorted(required), "at": now()}
            self.save(s, "TASK_EVIDENCE_RECORDED")
        return s["completedTasks"][task]

    def check(self, name):
        command = self.project()["commands"][name]
        with self.locked():
            s = self.load()
            if s["state"] in self.workflow()["terminalStates"] or s["state"] in SUSPENDED:
                raise ValueError("Cannot execute checks in terminal/suspended state")
            baseline = self.baseline(s)
            result = argv_run(command["argv"], safe(self.root, command.get("cwd", ".")), command.get("timeout", 120))
            log = self.folder / ("check-" + uuid.uuid4().hex + ".log")
            log.write_text(result.pop("output"), encoding="utf-8")
            result.update(name=name, baseline=baseline, at=now(), cwd=str(safe(self.root, command.get("cwd", "."))), log=log.relative_to(self.root).as_posix())
            result["logDigest"] = self.snapshot([result["log"]])
            if self.baseline(s) != baseline:
                result["exitCode"] = 125
                result["reason"] = "Verifier changed fingerprinted inputs"
            s["evidence"].append(result)
            self.save(s, "CHECK_RECORDED")
        return result

    def begin(self, operation, outputs, action="local_edit"):
        with self.locked():
            s = self.load()
            old = s["operations"].get(operation)
            if old:
                return {"replay": False, "operation": old, "instruction": "Inspect postconditions; reconcile rather than repeat"}
            if any(op["state"] == "started" for op in s["operations"].values()):
                raise ValueError("Another operation is pending; reconcile before a second writer")
            if s["state"] in SUSPENDED or s["state"] in self.workflow()["terminalStates"]:
                raise ValueError("Cannot begin operation in suspended/terminal state")
            if action in self.policy()["forbidden"]:
                raise ValueError("Forbidden operation: " + action)
            if action != "local_edit" and not self.authorized(s, action):
                raise ValueError("Action not authorized: " + action)
            op = {"id": operation, "state": "started", "outputs": outputs, "before": self.snapshot(outputs), "after": None, "action": action}
            s["operations"][operation] = op
            self.save(s, "OPERATION_STARTED")
        return {"replay": True, "operation": op}

    def complete(self, operation):
        with self.locked():
            s = self.load()
            op = s["operations"][operation]
            if op["state"] == "complete":
                if self.snapshot(op["outputs"]) != op["after"]:
                    raise ValueError("Completed operation outputs drifted")
                return op
            op.update(state="complete", after=self.snapshot(op["outputs"]))
            self.save(s, "OPERATION_COMPLETED")
        return op

    def reconcile(self, operation, expected):
        with self.locked():
            s = self.load()
            op = s["operations"][operation]
            if set(expected) != set(op["outputs"]):
                raise ValueError("Postconditions must cover every output")
            for relative, wanted in expected.items():
                p = safe(self.root, relative)
                actual = hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else "MISSING"
                if wanted != actual:
                    raise ValueError("Postcondition mismatch: " + relative)
            op.update(state="complete", after=self.snapshot(op["outputs"]), reconciled=True)
            self.save(s, "OPERATION_RECONCILED")
        return op

    def resume(self):
        with self.locked():
            s = self.load()
            if s["state"] == "AWAITING_DECISION":
                raise ValueError("Human decision is still pending")
            if s["state"] in SUSPENDED:
                s["state"], s["resumeState"] = s["resumeState"], None
            self.save(s, "RESUMED")
        return s

    def replace_decision(self, decision_id):
        """Invalidate a stale unanswered packet without claiming human approval."""
        with self.locked():
            s = self.load()
            d = next(d for d in s["decisions"] if d["id"] == decision_id)
            if s["state"] != "AWAITING_DECISION" or d["state"] != "pending":
                raise ValueError("Only pending decisions can be replaced")
            d["state"] = "superseded"
            s["state"], s["resumeState"] = s["resumeState"], None
            self.save(s, "DECISION_SUPERSEDED")
        return s

    def step(self, result):
        with self.locked():
            s, wf = self.load(), self.workflow()
            if s["state"] in wf["terminalStates"]:
                raise ValueError("Terminal run is immutable")
            allowed = {**wf["commonEvents"], **wf["states"].get(s["state"], {}).get("events", {})}
            if s["state"] in SUSPENDED:
                allowed = {"CANCEL": "CANCELLED", "REJECT": "REJECTED"} if s["state"] == "AWAITING_DECISION" else {"CANCEL": "CANCELLED"}
            try:
                validate(result, read(self.control / "skill-result.schema.json"))
                valid = result["event"] in allowed
            except ValueError:
                valid = False
            if not valid or s["state"] in wf["terminalStates"]:
                if s["state"] not in SUSPENDED:
                    s["resumeState"] = s["state"]
                s["state"] = "ERROR"
                s["diagnostic"] = "Invalid result/event: " + json.dumps(result)
                self.save(s, "INVALID_RESULT")
                return s
            event = result["event"]
            if event == "NEEDS_DECISION":
                raise ValueError("Use request_decision for a real decision packet")
            success = {"READY", "DELIVERY_READY", "AUTHORIZED", "VERIFIED", "LOCAL_COMPLETE", "LIGHT_COMPLETE", "DELIVERY_AUTHORIZED", "ARCHIVED", "SYNCED", "DELIVERED", "POST_VERIFIED", "CHANGE_REVIEWABLE", "ISSUE_READY", "LIGHT_READY", "IMPLEMENTATION_COMPLETE", "TASK_DONE", "UPDATED"}
            if event in success and (result["status"] != "completed" or result["readiness"] != "READY"):
                raise ValueError("Successful event requires completed/READY")
            if event == "READY" and not self.fresh_review(s, "design"):
                raise ValueError("Fresh ready design review required")
            if event == "DELIVERY_READY" and (not s["contract"] or not self.fresh_review(s, "planning")):
                raise ValueError("Contract and fresh planning review required")
            if event == "AUTHORIZED" and not self.authorized(s, "implement"):
                raise ValueError("User has not authorized this implementation scope")
            if event in {"VERIFIED", "LOCAL_COMPLETE", "LIGHT_COMPLETE", "DELIVERY_AUTHORIZED"}:
                status = self.evidence_status(s)
                if not status["ok"]:
                    raise ValueError("Evidence gate: " + "; ".join(status["gaps"]))
            if event == "LOCAL_COMPLETE" and (s["mode"] != "full" or self.project()["endpoint"] != "local"):
                raise ValueError("Local/full completion mismatch")
            if event == "LIGHT_COMPLETE" and (s["mode"] != "light" or self.project()["endpoint"] != "local"):
                raise ValueError("Only local light delivery bypasses archive")
            if event == "DELIVERY_AUTHORIZED":
                endpoint = self.project()["endpoint"]
                if endpoint == "local" or not self.authorized(s, endpoint):
                    raise ValueError("External delivery requires endpoint-specific approval")
            if event in {"SYNCED", "ARCHIVED", "DELIVERED", "POST_VERIFIED"}:
                op = s["operations"].get(event.lower(), {})
                if op.get("state") != "complete" or self.snapshot(op["outputs"]) != op["after"]:
                    raise ValueError("Current operation receipt required: " + event)
            if event in {"AUTO_FIXABLE", "REPAIRABLE_FAILURE"}:
                key = digest([s["state"], result.get("details", "unspecified failure")])
                count = s["failures"].get(key, 0) + 1
                s["failures"][key] = count
                if count > self.policy()["maxRepairAttempts"]:
                    s["resumeState"], s["state"] = s["state"], "PAUSED"
                    s["diagnostic"] = "Repair budget exhausted: " + key
                    self.save(s, "RETRY_EXHAUSTED")
                    return s
            target = allowed[event]
            if target in SUSPENDED:
                s["resumeState"] = s["state"]
                s["diagnostic"] = result.get("details", event)
            s["state"] = target
            self.save(s, event)
        return s


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("action", choices=["scan", "init", "doctor", "start", "status", "bind", "step", "request_decision", "decide", "replace_decision", "resume", "review", "check", "finish_task", "evidence_status", "begin", "complete", "reconcile", "package"])
    parser.add_argument("--run")
    parser.add_argument("--input", type=Path, help="JSON keyword arguments")
    args = parser.parse_args()
    try:
        params = read(args.input) if args.input else {}
        c = Controller(args.root, args.run)
        result = package_skill(**params) if args.action == "package" else scan(c.root) if args.action == "scan" else c.load() if args.action == "status" else getattr(c, args.action)(**params)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if args.action == "doctor" and not result["ok"] else 0
    except (OSError, ValueError, KeyError, TypeError, StopIteration) as exc:
        print(json.dumps({"error": str(exc)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
