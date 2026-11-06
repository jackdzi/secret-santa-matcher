"""The verifier on correct, wrong, missing, malformed and boundary results."""

from __future__ import annotations

from pathlib import Path

import pytest
from helpers import as_sandbox, feasible_seed, gold_run, task
from slimconfig import build_output, plain_output

import verifier
from contract import AssignmentOutput, CheckInput, CheckOutput, GroupOutput
from plugin import check_assignment, get_group, pin_feasibility
from plugin.santa import make_group

TASK = "match-gifts"


def judge(given, output: dict, tmp_path: Path) -> dict:
    reference = as_sandbox(pin_feasibility(given, tmp_path), type(pin_feasibility(given, tmp_path)))
    return verifier.verify_task(TASK, given, as_sandbox(output, AssignmentOutput), reference, str(tmp_path))


def gold_pairs(given, tmp_path: Path) -> list[dict]:
    output, _ = gold_run(given, tmp_path)
    assert output.status.value == "assigned"
    return [plain_output(p) for p in output.pairs]


@pytest.mark.parametrize("rule", ["any", "single-cycle"])
def test_accepts_a_valid_assignment(tmp_path: Path, rule: str) -> None:
    given = task(feasible_seed(7, rule, True), 7, rule)
    output, reference = gold_run(given, tmp_path)
    verdict = verifier.verify_task(TASK, given, output, reference, str(tmp_path))
    assert verdict["valid"] is True and verdict["score"] == 1.0, verdict["message"]


@pytest.mark.parametrize("rule", ["any", "single-cycle"])
def test_accepts_impossible_for_an_impossible_group(tmp_path: Path, rule: str) -> None:
    given = task(feasible_seed(7, rule, False), 7, rule)
    verdict = judge(given, {"status": "impossible", "pairs": []}, tmp_path)
    assert verdict["valid"] is True and verdict["details"]["valid_assignments"] == 0


def test_rejects_impossible_for_a_possible_group(tmp_path: Path) -> None:
    given = task(feasible_seed(6, "any", True), 6, "any")
    verdict = judge(given, {"status": "impossible", "pairs": []}, tmp_path)
    assert verdict["valid"] is False and verdict["details"]["valid_assignments"] > 0


def test_rejects_an_assignment_for_an_impossible_group(tmp_path: Path) -> None:
    given = task(feasible_seed(6, "any", False), 6, "any")
    people, _ = make_group(given)
    rotated = [{"giver": p, "receiver": people[(i + 1) % len(people)]} for i, p in enumerate(people)]
    verdict = judge(given, {"status": "assigned", "pairs": rotated}, tmp_path)
    assert verdict["valid"] is False and verdict["details"]["broken_rules"]


def test_rejects_impossible_with_pairs_listed(tmp_path: Path) -> None:
    given = task(feasible_seed(6, "any", False), 6, "any")
    verdict = judge(given, {"status": "impossible", "pairs": [{"giver": "Ava", "receiver": "Ben"}]}, tmp_path)
    assert verdict["valid"] is False


def test_rejects_a_self_gift(tmp_path: Path) -> None:
    given = task(feasible_seed(6, "any", True), 6, "any")
    pairs = gold_pairs(given, tmp_path)
    pairs[0]["receiver"] = pairs[0]["giver"]
    verdict = judge(given, {"status": "assigned", "pairs": pairs}, tmp_path)
    assert verdict["valid"] is False and any(rule.startswith("self-gift") for rule in verdict["details"]["broken_rules"])


def test_rejects_an_excluded_pair(tmp_path: Path) -> None:
    seed = next(s for s in range(1000) if make_group(task(s, 6, "any"))[1] and pin_feasibility(task(s, 6, "any"), tmp_path).feasible)
    given = task(seed, 6, "any")
    people, excluded = make_group(given)
    giver, receiver = next(iter(excluded))
    pairs = [{"giver": p, "receiver": people[(i + 1) % len(people)]} for i, p in enumerate(people)]
    for pair in pairs:
        if pair["giver"] == giver:
            pair["receiver"] = receiver
    verdict = judge(given, {"status": "assigned", "pairs": pairs}, tmp_path)
    assert verdict["valid"] is False and any(rule.startswith("excluded") for rule in verdict["details"]["broken_rules"])


def test_rejects_a_missing_person(tmp_path: Path) -> None:
    given = task(feasible_seed(6, "any", True), 6, "any")
    verdict = judge(given, {"status": "assigned", "pairs": gold_pairs(given, tmp_path)[1:]}, tmp_path)
    broken = verdict["details"]["broken_rules"]
    assert verdict["valid"] is False and any(r.startswith("never-gives") for r in broken)


def test_rejects_a_receiver_given_twice(tmp_path: Path) -> None:
    given = task(feasible_seed(6, "any", True), 6, "any")
    pairs = gold_pairs(given, tmp_path)
    pairs[1]["receiver"] = pairs[0]["receiver"]
    verdict = judge(given, {"status": "assigned", "pairs": pairs}, tmp_path)
    assert verdict["valid"] is False and any(r.startswith("receives-twice") for r in verdict["details"]["broken_rules"])


def test_rejects_an_unknown_person(tmp_path: Path) -> None:
    given = task(feasible_seed(6, "any", True), 6, "any")
    pairs = gold_pairs(given, tmp_path)
    pairs[0]["receiver"] = "Santa"
    verdict = judge(given, {"status": "assigned", "pairs": pairs}, tmp_path)
    assert verdict["valid"] is False and "unknown-person: Santa" in verdict["details"]["broken_rules"]


def test_rejects_an_empty_assignment(tmp_path: Path) -> None:
    given = task(feasible_seed(6, "any", True), 6, "any")
    verdict = judge(given, {"status": "assigned", "pairs": []}, tmp_path)
    assert verdict["valid"] is False and verdict["score"] == 0.0


def test_rejects_two_loops_under_single_cycle(tmp_path: Path) -> None:
    # Two loops are valid under any but not under single-cycle: find a group where an any-assignment splits.
    for seed in range(2000):
        given_any, given_loop = task(seed, 6, "any"), task(seed, 6, "single-cycle")
        people, excluded = make_group(given_loop)
        halves = [people[:3], people[3:]]
        pairs = [{"giver": h[i], "receiver": h[(i + 1) % 3]} for h in halves for i in range(3)]
        if all((p["giver"], p["receiver"]) not in excluded for p in pairs) and pin_feasibility(given_loop, tmp_path).feasible:
            break
    else:
        pytest.fail("no group allows two loops of three")
    verdict = judge(given_loop, {"status": "assigned", "pairs": pairs}, tmp_path)
    assert verdict["valid"] is False and any(r.startswith("not-one-cycle") for r in verdict["details"]["broken_rules"])
    assert given_any.rule.value == "any"


def test_rejects_a_tampered_answer_key(tmp_path: Path) -> None:
    given = task(feasible_seed(6, "any", True), 6, "any")
    output, reference = gold_run(given, tmp_path)
    reference.count += 1
    assert verifier.verify_task(TASK, given, output, reference, str(tmp_path))["valid"] is False


@pytest.mark.parametrize("rule", ["any", "single-cycle"])
@pytest.mark.parametrize("size", [2, 3, 10])
@pytest.mark.parametrize("seed", range(8))
def test_boundary_sizes(tmp_path: Path, rule: str, size: int, seed: int) -> None:
    given = task(seed, size, rule)
    output, reference = gold_run(given, tmp_path)
    assert verifier.verify_task(TASK, given, output, reference, str(tmp_path))["valid"] is True


def test_two_people_have_exactly_one_assignment_unless_excluded(tmp_path: Path) -> None:
    for seed in range(50):
        pinned = pin_feasibility(task(seed, 2, "any"), tmp_path)
        assert pinned.count in (0, 1)


def test_input_checks_refuse_a_malformed_task() -> None:
    for bad in (task(seed=-1), task(size=1), task(size=11)):
        assert verifier.verify_input("get_group", bad)["valid"] is False
    check = build_output({"task": {"seed": 1, "size": 12, "rule": "any"}, "pairs": []}, CheckInput)
    assert verifier.verify_input("check_assignment", check)["valid"] is False


def test_tool_outputs_are_checked(tmp_path: Path) -> None:
    given = task(3, 8, "single-cycle")
    group = as_sandbox(get_group(given, tmp_path), GroupOutput)
    assert verifier.verify_output("get_group", given, group, str(tmp_path))["valid"] is True
    group.exclusions = group.exclusions[1:]
    assert verifier.verify_output("get_group", given, group, str(tmp_path))["valid"] is False
    check = build_output({"task": plain_output(given), "pairs": [{"giver": "Nobody", "receiver": "Nobody"}]}, CheckInput)
    checked = as_sandbox(check_assignment(check, tmp_path), CheckOutput)
    assert verifier.verify_output("check_assignment", check, checked, str(tmp_path))["valid"] is True
    checked.problems = checked.problems[1:]
    assert verifier.verify_output("check_assignment", check, checked, str(tmp_path))["valid"] is False


def test_the_check_counter_is_verified(tmp_path: Path) -> None:
    given = task(3, 6, "any")
    people = get_group(given, tmp_path).people
    pairs = [{"giver": p, "receiver": people[(i + 1) % len(people)]} for i, p in enumerate(people)]
    check = build_output({"task": plain_output(given), "pairs": pairs}, CheckInput)
    checked = as_sandbox(check_assignment(check, tmp_path), CheckOutput)
    assert verifier.verify_output("check_assignment", check, checked, str(tmp_path))["valid"] is True
    checked.checks_left = 2
    assert verifier.verify_output("check_assignment", check, checked, str(tmp_path))["valid"] is False


def test_always_answering_impossible_is_right_only_a_fifth_of_the_time(tmp_path: Path) -> None:
    right = 0
    for seed in range(100):
        given = task(seed, 3 + seed % 8, "any")
        _, reference = gold_run(given, tmp_path / str(seed))
        guess = as_sandbox({"status": "impossible", "pairs": []}, AssignmentOutput)
        right += verifier.verify_task("match-gifts", given, guess, reference, str(tmp_path))["valid"]
    assert right <= 30
