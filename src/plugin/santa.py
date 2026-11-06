"""The gift-exchange groups, the rule checks, a backtracking solver, and the three tools."""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path

from contract import (
    Allowed,
    CheckInput,
    CheckOutput,
    Exclusion,
    GroupInput,
    GroupOutput,
    Pair,
    PinOutput,
    Problem,
    ProblemKind,
    Reason,
    Rule,
)
from plugin.rng import Stream, canonical_sha256

MAX_SEED = 1_000_000_000
MIN_SIZE, MAX_SIZE = 2, 10
MAX_DRAWS = 500
MAX_CHECKS = 2
NAMES = (
    "Ava", "Ben", "Cleo", "Dev", "Ezra", "Fay", "Gus", "Hana", "Ivan", "Jade",
    "Kai", "Lena", "Milo", "Nora", "Omar", "Pia", "Quinn", "Rosa", "Sam", "Tess",
    "Uma", "Vik", "Wren", "Xia", "Yusuf", "Zoe", "Ari", "Bea", "Cyd", "Dana",
    "Eli", "Finn", "Gia", "Hugo", "Iris", "Jon", "Kira", "Leo", "Maya", "Nico",
)


def check_task(task: GroupInput) -> None:
    if not 0 <= task.seed <= MAX_SEED:
        raise ValueError(f"seed must be from 0 to {MAX_SEED}")
    if not MIN_SIZE <= task.size <= MAX_SIZE:
        raise ValueError(f"size must be from {MIN_SIZE} to {MAX_SIZE}")


def make_group(task: GroupInput) -> tuple[list[str], dict[tuple[str, str], Reason]]:
    """The people and every excluded (giver, receiver) with its reason.

    The seed first decides whether the group is possible (4 in 5) or impossible (1 in 5), at every
    size alike, then exclusions are drawn (draw n from its own stream) until the group is the kind
    decided: so an agent that always answers impossible is right only a fifth of the time."""
    check_task(task)
    key = f"{task.seed}|{task.size}|{task.rule.value}"
    stream = Stream("santa", key)
    people = stream.shuffled(NAMES)[: task.size]
    possible = not stream.chance(1, 5)
    for draw in range(MAX_DRAWS):
        excluded = draw_exclusions(Stream("santa-draw", f"{key}|{draw}"), people)
        if (solve(people, excluded, task.rule)[1] > 0) == possible:
            return people, excluded
    raise RuntimeError(f"no {'possible' if possible else 'impossible'} group in {MAX_DRAWS} draws for {key}")


def draw_exclusions(stream: Stream, people: list[str]) -> dict[tuple[str, str], Reason]:
    """Couples exclude each other both ways, a household of three all exclude each other, some people
    may not repeat last year's receiver, and about a sixth of draws add requests that leave a group of
    k + 1 givers only k possible receivers, which no assignment can satisfy."""
    size = len(people)
    excluded: dict[tuple[str, str], Reason] = {}

    def exclude(giver: str, receiver: str, reason: Reason) -> None:
        if giver != receiver and (giver, receiver) not in excluded:
            excluded[(giver, receiver)] = reason

    order = stream.shuffled(people)
    for i in range(0, len(order) - 1, 2):
        if stream.chance(1, 3):
            exclude(order[i], order[i + 1], Reason.COUPLE)
            exclude(order[i + 1], order[i], Reason.COUPLE)
    if size >= 6 and stream.chance(1, 3):
        household = stream.shuffled(people)[:3]
        for giver in household:
            for receiver in household:
                exclude(giver, receiver, Reason.HOUSEHOLD)
    for giver in people:
        if stream.chance(1, 3):
            exclude(giver, stream.choice([p for p in people if p != giver]), Reason.LAST_YEAR)
    if stream.chance(1, 6):
        k = stream.between(1, size - 1)
        givers, receivers = stream.shuffled(people)[: k + 1], stream.shuffled(people)[:k]
        for giver in givers:
            for receiver in people:
                if receiver not in receivers:
                    exclude(giver, receiver, Reason.REQUEST)
    return excluded


def group_sha256(people: list[str], excluded: dict[tuple[str, str], Reason], rule: Rule) -> str:
    pairs = sorted([giver, receiver, reason.value] for (giver, receiver), reason in excluded.items())
    return canonical_sha256({"people": people, "exclusions": pairs, "rule": rule.value})


def allowed_receivers(people: list[str], excluded: dict[tuple[str, str], Reason]) -> dict[str, list[str]]:
    return {g: [r for r in people if r != g and (g, r) not in excluded] for g in people}


def problems(people: list[str], excluded: dict[tuple[str, str], Reason], rule: Rule, pairs: list[Pair]) -> list[Problem]:
    """Every rule ``pairs`` breaks, in a fixed order."""
    known = set(people)
    found: list[Problem] = []
    gives: dict[str, list[str]] = {p: [] for p in people}
    gets: dict[str, list[str]] = {p: [] for p in people}
    for pair in pairs:
        for name in (pair.giver, pair.receiver):
            if name not in known:
                found.append(Problem(kind=ProblemKind.UNKNOWN_PERSON, person=name, detail=f"{name} is not in the group"))
        if pair.giver in known and pair.receiver in known:
            gives[pair.giver].append(pair.receiver)
            gets[pair.receiver].append(pair.giver)
            if pair.giver == pair.receiver:
                found.append(Problem(kind=ProblemKind.SELF_GIFT, person=pair.giver, detail=f"{pair.giver} gives to themselves"))
            elif (pair.giver, pair.receiver) in excluded:
                reason = excluded[(pair.giver, pair.receiver)].value
                found.append(
                    Problem(kind=ProblemKind.EXCLUDED, person=pair.giver, detail=f"{pair.giver} may not give to {pair.receiver} ({reason})")
                )
    for person in people:
        if len(gives[person]) > 1:
            found.append(Problem(kind=ProblemKind.GIVES_TWICE, person=person, detail=f"{person} gives {len(gives[person])} gifts"))
        if not gives[person]:
            found.append(Problem(kind=ProblemKind.NEVER_GIVES, person=person, detail=f"{person} gives no gift"))
        if len(gets[person]) > 1:
            found.append(Problem(kind=ProblemKind.RECEIVES_TWICE, person=person, detail=f"{person} receives {len(gets[person])} gifts"))
        if not gets[person]:
            found.append(Problem(kind=ProblemKind.NEVER_RECEIVES, person=person, detail=f"{person} receives no gift"))
    if rule is Rule.SINGLE_CYCLE and not found:
        loop, at = 1, gives[people[0]][0]
        while at != people[0]:
            loop, at = loop + 1, gives[at][0]
        if loop != len(people):
            found.append(
                Problem(
                    kind=ProblemKind.NOT_ONE_CYCLE,
                    person=people[0],
                    detail=f"starting from {people[0]}, the loop returns after {loop} of {len(people)} people",
                )
            )
    # One problem per (kind, person): the first found.
    unique: dict[tuple[ProblemKind, str], Problem] = {}
    for problem in found:
        unique.setdefault((problem.kind, problem.person), problem)
    return list(unique.values())


def solve(people: list[str], excluded: dict[tuple[str, str], Reason], rule: Rule) -> tuple[list[Pair], int]:
    """One valid assignment (empty if none) and how many exist, by backtracking with memoised counts."""
    allowed = allowed_receivers(people, excluded)
    index = {p: i for i, p in enumerate(people)}
    n = len(people)
    full = (1 << n) - 1

    if rule is Rule.ANY:
        # Giver i takes an unused receiver; `used` is the set of receivers taken so far.
        @cache
        def count(i: int, used: int) -> int:
            if i == n:
                return 1
            return sum(count(i + 1, used | 1 << index[r]) for r in allowed[people[i]] if not used >> index[r] & 1)

        def example(i: int, used: int) -> list[Pair] | None:
            if i == n:
                return []
            for r in allowed[people[i]]:
                if not used >> index[r] & 1 and count(i + 1, used | 1 << index[r]):
                    return [Pair(giver=people[i], receiver=r), *example(i + 1, used | 1 << index[r])]
            return None

        total = count(0, 0)
        return (example(0, 0) or []) if total else [], total

    # One loop: a path from the first person through everyone, then back to the first person.
    first = people[0]

    @cache
    def paths(at: str, seen: int) -> int:
        if seen == full:
            return 1 if first in allowed[at] else 0
        return sum(paths(r, seen | 1 << index[r]) for r in allowed[at] if not seen >> index[r] & 1)

    def walk(at: str, seen: int) -> list[Pair]:
        if seen == full:
            return [Pair(giver=at, receiver=first)]
        for r in allowed[at]:
            if not seen >> index[r] & 1 and paths(r, seen | 1 << index[r]):
                return [Pair(giver=at, receiver=r), *walk(r, seen | 1 << index[r])]
        raise AssertionError("a counted path was not found")

    total = paths(first, 1 << index[first]) if n > 1 else 0
    if not total:
        return [], 0
    pairs = walk(first, 1 << index[first])
    return sorted(pairs, key=lambda p: index[p.giver]), total


def get_group(task: GroupInput, workspace: Path) -> GroupOutput:
    people, excluded = make_group(task)
    order = {p: i for i, p in enumerate(people)}
    exclusions = [
        Exclusion(giver=g, receiver=r, reason=reason)
        for (g, r), reason in sorted(excluded.items(), key=lambda item: (order[item[0][0]], order[item[0][1]]))
    ]
    allowed = allowed_receivers(people, excluded)
    return GroupOutput(
        people=people,
        rule=task.rule,
        exclusions=exclusions,
        allowed=[Allowed(giver=g, receivers=allowed[g]) for g in people],
    )


def checks_path(task: GroupInput) -> str:
    return f"santa/{task.rule.value}-{task.size}-{task.seed}.checks.json"


def check_assignment(check: CheckInput, workspace: Path) -> CheckOutput:
    """The rules an assignment breaks. A task allows MAX_CHECKS checks: the count is kept in the workspace."""
    path = workspace / checks_path(check.task)
    used = json.loads(path.read_text(encoding="utf-8"))["checks"] if path.is_file() else 0
    if used >= MAX_CHECKS:
        raise ValueError(f"check_assignment allows {MAX_CHECKS} checks per task and both are used: decide and submit")
    people, excluded = make_group(check.task)
    found = problems(people, excluded, check.task.rule, check.pairs)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"checks": used + 1}), encoding="utf-8")
    return CheckOutput(valid=not found, problems=found, checks_left=MAX_CHECKS - used - 1)


def pin_feasibility(task: GroupInput, workspace: Path) -> PinOutput:
    people, excluded = make_group(task)
    example, total = solve(people, excluded, task.rule)
    return PinOutput(group_sha256=group_sha256(people, excluded, task.rule), feasible=total > 0, example=example, count=total)
