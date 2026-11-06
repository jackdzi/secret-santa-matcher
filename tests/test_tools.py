"""The tools, the independent oracle, and the MCP server."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import anyio
from helpers import task
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from slimconfig import build_output, plain_output

from contract import CheckInput, ProblemKind, Reason, Rule
from plugin import check_assignment, get_group, pin_feasibility
from plugin.santa import make_group, problems, solve
from verifier.santa import broken_rules, count_valid, rebuild_group

ROOT = Path(__file__).resolve().parents[1]


def test_a_group_is_the_same_for_the_same_seed(tmp_path: Path) -> None:
    assert get_group(task(seed=5), tmp_path) == get_group(task(seed=5), tmp_path)
    assert get_group(task(seed=5), tmp_path) != get_group(task(seed=6), tmp_path)


def test_couples_exclude_each_other_both_ways(tmp_path: Path) -> None:
    for seed in range(200):
        _, excluded = make_group(task(seed, 8))
        for (giver, receiver), reason in excluded.items():
            if reason is Reason.COUPLE:
                assert excluded.get((receiver, giver)) is Reason.COUPLE


def test_allowed_lists_match_the_exclusions(tmp_path: Path) -> None:
    group = get_group(task(9, 10), tmp_path)
    excluded = {(e.giver, e.receiver) for e in group.exclusions}
    for entry in group.allowed:
        assert entry.receivers == [p for p in group.people if p != entry.giver and (entry.giver, p) not in excluded]


def test_known_counts_without_exclusions() -> None:
    # Derangements of n (any) and (n-1)! loops through everyone (single-cycle).
    people = ["A", "B", "C", "D", "E"]
    assert solve(people, {}, Rule.ANY)[1] == 44
    assert solve(people, {}, Rule.SINGLE_CYCLE)[1] == 24
    assert solve(["A", "B"], {}, Rule.SINGLE_CYCLE)[1] == 1
    assert solve(["A", "B"], {("A", "B"): Reason.COUPLE}, Rule.ANY) == ([], 0)


def test_the_tool_and_the_verifier_agree_on_2000_groups(tmp_path: Path) -> None:
    for seed in range(1000):
        for rule in ("any", "single-cycle"):
            given = task(seed, 2 + seed % 9, rule)
            people, excluded = make_group(given)
            assert (people, {k: v.value for k, v in excluded.items()}) == rebuild_group(given)
            example, total = solve(people, excluded, given.rule)
            assert total == count_valid(given), (seed, rule)
            if total:
                assert not problems(people, excluded, given.rule, example)


def test_about_a_fifth_of_groups_are_impossible_at_every_size(tmp_path: Path) -> None:
    # Small groups would be mostly impossible if exclusions were drawn freely; the seed fixes the kind.
    for size in (2, 3, 6, 10):
        impossible = sum(not pin_feasibility(task(seed, size, "any"), tmp_path).feasible for seed in range(150))
        assert 15 <= impossible <= 45, (size, impossible)


def test_every_seed_finds_a_group_of_its_kind(tmp_path: Path) -> None:
    for rule in ("any", "single-cycle"):
        for size in range(2, 11):
            for seed in range(40):
                assert rebuild_group(task(seed, size, rule))[1] is not None


def test_check_assignment_allows_two_checks(tmp_path: Path) -> None:
    import pytest

    given = task(3, 6, "any")
    people = get_group(given, tmp_path).people
    pairs = [{"giver": p, "receiver": people[(i + 1) % len(people)]} for i, p in enumerate(people)]
    check = build_output({"task": plain_output(given), "pairs": pairs}, CheckInput)
    assert check_assignment(check, tmp_path).checks_left == 1
    assert check_assignment(check, tmp_path).checks_left == 0
    with pytest.raises(ValueError, match="2 checks"):
        check_assignment(check, tmp_path)
    # Another task has its own two checks.
    other = build_output({"task": plain_output(task(4, 6, "any")), "pairs": pairs}, CheckInput)
    assert check_assignment(other, tmp_path).checks_left == 1


def test_the_tool_check_and_the_verifier_check_agree(tmp_path: Path) -> None:
    for seed in range(200):
        given = task(seed, 6, "single-cycle" if seed % 2 else "any")
        people, excluded = make_group(given)
        shift = 1 + seed % 5
        pairs = [{"giver": p, "receiver": people[(i + shift) % len(people)]} for i, p in enumerate(people)]
        if seed % 7 == 0:
            pairs = pairs[1:] + [{"giver": "Ghost", "receiver": people[0]}]
        check = build_output({"task": plain_output(given), "pairs": pairs}, CheckInput)
        found = check_assignment(check, tmp_path)
        assert {(p.kind.value, p.person) for p in found.problems} == broken_rules(people, {k: v.value for k, v in excluded.items()}, given.rule.value, check.pairs)
        assert found.valid == (not found.problems)


def test_check_reports_two_loops(tmp_path: Path) -> None:
    people = ["A", "B", "C", "D"]
    from contract import Pair

    pairs = [Pair(giver="A", receiver="B"), Pair(giver="B", receiver="A"), Pair(giver="C", receiver="D"), Pair(giver="D", receiver="C")]
    assert [p.kind for p in problems(people, {}, Rule.SINGLE_CYCLE, pairs)] == [ProblemKind.NOT_ONE_CYCLE]
    assert problems(people, {}, Rule.ANY, pairs) == []


def test_the_mcp_server_lists_and_runs_every_tool(tmp_path: Path) -> None:
    async def run() -> None:
        params = StdioServerParameters(
            command=sys.executable, args=["-m", "plugin"], cwd=str(ROOT), env={**os.environ, "NANOAGENT_WORKSPACE": str(tmp_path)}
        )
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            names = {tool.name for tool in (await session.list_tools()).tools}
            assert names == {"get_group", "check_assignment", "pin_feasibility"}
            given = {"seed": 1, "size": 5, "rule": "any"}
            group = await session.call_tool("get_group", given)
            assert not group.isError and len(group.structuredContent["people"]) == 5
            checked = await session.call_tool("check_assignment", {"task": given, "pairs": []})
            assert not checked.isError and checked.structuredContent["valid"] is False
            pinned = await session.call_tool("pin_feasibility", given)
            assert not pinned.isError
            bad = await session.call_tool("get_group", {"seed": 1, "size": 11, "rule": "any"})
            assert bad.isError

    anyio.run(run)
