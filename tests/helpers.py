from __future__ import annotations

from pathlib import Path

from scripted_agent import assignment_from_group
from slimconfig import build_output, plain_output

from contract import AssignmentOutput, CheckInput, GroupInput, PinOutput
from plugin import check_assignment, get_group, pin_feasibility


def as_sandbox(value, cls):
    """A value as NanoAgent's verifier sandbox hands it over: rebuilt from its JSON."""
    return build_output(plain_output(value) if not isinstance(value, dict) else value, cls)


def task(seed: int = 7, size: int = 6, rule: str = "any") -> GroupInput:
    return build_output({"seed": seed, "size": size, "rule": rule}, GroupInput)


def gold_run(given: GroupInput, workspace: Path) -> tuple[AssignmentOutput, PinOutput]:
    """A correct run through the real tools: get_group, check_assignment, and the submitted output."""
    group = get_group(given, workspace)
    allowed = {entry.giver: entry.receivers for entry in group.allowed}
    pairs = assignment_from_group(group.people, allowed, given.rule.value)
    if pairs is None:
        output = {"status": "impossible", "pairs": []}
    else:
        checked = check_assignment(build_output({"task": plain_output(given), "pairs": pairs}, CheckInput), workspace)
        assert checked.valid, checked.problems
        output = {"status": "assigned", "pairs": pairs}
    reference = as_sandbox(pin_feasibility(given, workspace), PinOutput)
    return as_sandbox(output, AssignmentOutput), reference


def feasible_seed(size: int, rule: str, want: bool) -> int:
    """The first seed whose group of ``size`` under ``rule`` is (or is not) possible."""
    return next(seed for seed in range(10_000) if pin_feasibility(task(seed, size, rule), Path(".")).feasible is want)
