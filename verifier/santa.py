"""The gift-exchange verifier. It rebuilds each group from its seed and decides on its own whether a
valid assignment exists, by counting them all with bottom-up dynamic programming over sets of
people: assignments for the rule any (the permanent of the allowed matrix), and loops through
everyone for single-cycle. The tools search by backtracking instead; the two must agree. A count of
0 is an exhaustive proof that the group is impossible."""

import json
from pathlib import Path

from .checks import result
from .rng import Stream, canonical_sha256

MAX_SEED = 1_000_000_000
MAX_DRAWS = 500
MAX_CHECKS = 2
NAMES = (
    "Ava", "Ben", "Cleo", "Dev", "Ezra", "Fay", "Gus", "Hana", "Ivan", "Jade",
    "Kai", "Lena", "Milo", "Nora", "Omar", "Pia", "Quinn", "Rosa", "Sam", "Tess",
    "Uma", "Vik", "Wren", "Xia", "Yusuf", "Zoe", "Ari", "Bea", "Cyd", "Dana",
    "Eli", "Finn", "Gia", "Hugo", "Iris", "Jon", "Kira", "Leo", "Maya", "Nico",
)


def task_problem(task):
    if not 0 <= task.seed <= MAX_SEED:
        return f"seed must be from 0 to {MAX_SEED}"
    if not 2 <= task.size <= 10:
        return "size must be from 2 to 10"
    if rebuild_group(task)[1] is None:
        return f"no group of the decided kind was found in {MAX_DRAWS} draws for this seed"
    return None


def rebuild_group(task):
    """(people, {(giver, receiver): reason}), drawn exactly as the get_group tool draws them: the seed
    decides whether the group is possible (4 in 5), and exclusions are drawn until it is that kind,
    judged by the verifier's own count."""
    key = f"{task.seed}|{task.size}|{task.rule.value}"
    stream = Stream("santa", key)
    people = stream.shuffled(NAMES)[: task.size]
    possible = not stream.chance(1, 5)
    for draw in range(MAX_DRAWS):
        excluded = draw_exclusions(Stream("santa-draw", f"{key}|{draw}"), people)
        if (count_for(people, excluded, task.rule.value) > 0) == possible:
            return people, excluded
    return people, None


def draw_exclusions(stream, people):
    size = len(people)
    excluded = {}

    def exclude(giver, receiver, reason):
        if giver != receiver and (giver, receiver) not in excluded:
            excluded[(giver, receiver)] = reason

    order = stream.shuffled(people)
    for i in range(0, len(order) - 1, 2):
        if stream.chance(1, 3):
            exclude(order[i], order[i + 1], "couple")
            exclude(order[i + 1], order[i], "couple")
    if size >= 6 and stream.chance(1, 3):
        household = stream.shuffled(people)[:3]
        for giver in household:
            for receiver in household:
                exclude(giver, receiver, "household")
    for giver in people:
        if stream.chance(1, 3):
            exclude(giver, stream.choice([p for p in people if p != giver]), "last-year")
    if stream.chance(1, 6):
        k = stream.between(1, size - 1)
        givers, receivers = stream.shuffled(people)[: k + 1], stream.shuffled(people)[:k]
        for giver in givers:
            for receiver in people:
                if receiver not in receivers:
                    exclude(giver, receiver, "request")
    return excluded


def group_hash(people, excluded, rule):
    pairs = sorted([g, r, reason] for (g, r), reason in excluded.items())
    return canonical_sha256({"people": people, "exclusions": pairs, "rule": rule})


def can_give(people, excluded):
    """can[i][j]: person i may give to person j."""
    return [[i != j and (g, r) not in excluded for j, r in enumerate(people)] for i, g in enumerate(people)]


def count_assignments(can):
    """How many ways every person gives once and receives once: ways[mask] counts the ways to give
    gifts from the first popcount(mask) givers to exactly the receivers in mask."""
    n = len(can)
    ways = [0] * (1 << n)
    ways[0] = 1
    for mask in range(1 << n):
        if not ways[mask]:
            continue
        giver = mask.bit_count()
        if giver == n:
            continue
        for receiver in range(n):
            if can[giver][receiver] and not mask & (1 << receiver):
                ways[mask | (1 << receiver)] += ways[mask]
    return ways[(1 << n) - 1]


def count_loops(can):
    """How many single loops through everyone: paths[mask][v] counts the paths from person 0 that
    visit exactly mask and end at v; a loop is a full path whose end may give back to person 0."""
    n = len(can)
    paths = [[0] * n for _ in range(1 << n)]
    paths[1][0] = 1
    for mask in range(1 << n):
        if not mask & 1:
            continue
        for v in range(n):
            if not paths[mask][v]:
                continue
            for w in range(n):
                if can[v][w] and not mask & (1 << w):
                    paths[mask | (1 << w)][w] += paths[mask][v]
    full = (1 << n) - 1
    return sum(paths[full][v] for v in range(1, n) if can[v][0])


def count_for(people, excluded, rule):
    can = can_give(people, excluded)
    return count_loops(can) if rule == "single-cycle" else count_assignments(can)


def count_valid(task):
    people, excluded = rebuild_group(task)
    return count_for(people, excluded, task.rule.value)


def broken_rules(people, excluded, rule, pairs):
    """{(kind, person)} for every rule the pairs break, computed from giver and receiver tallies."""
    known = set(people)
    broken = set()
    targets = {}
    gifts_given = {p: 0 for p in people}
    gifts_got = {p: 0 for p in people}
    for pair in pairs:
        g, r = pair.giver, pair.receiver
        broken |= {("unknown-person", name) for name in (g, r) if name not in known}
        if g not in known or r not in known:
            continue
        gifts_given[g] += 1
        gifts_got[r] += 1
        targets[g] = r
        if g == r:
            broken.add(("self-gift", g))
        elif (g, r) in excluded:
            broken.add(("excluded", g))
    for p in people:
        if gifts_given[p] > 1:
            broken.add(("gives-twice", p))
        if gifts_given[p] == 0:
            broken.add(("never-gives", p))
        if gifts_got[p] > 1:
            broken.add(("receives-twice", p))
        if gifts_got[p] == 0:
            broken.add(("never-receives", p))
    if rule == "single-cycle" and not broken:
        seen, at = {people[0]}, targets[people[0]]
        while at not in seen:
            seen.add(at)
            at = targets[at]
        if len(seen) != len(people):
            broken.add(("not-one-cycle", people[0]))
    return broken


def describe(broken):
    return [f"{kind}: {person}" for kind, person in sorted(broken)]


def verify_group_input(value):
    problem = task_problem(value)
    return result(False, problem) if problem else result(True, "input is valid")


def verify_check_input(value):
    return verify_group_input(value.task)


def verify_group_output(task, output):
    people, excluded = rebuild_group(task)
    given = {(e.giver, e.receiver): e.reason.value for e in output.exclusions}
    if output.people != people or given != excluded or len(given) != len(output.exclusions):
        return result(False, "the group is not the one the seed gives")
    can = can_give(people, excluded)
    for i, entry in enumerate(output.allowed):
        expected = [people[j] for j in range(len(people)) if can[i][j]] if i < len(people) else None
        if entry.giver != (people[i] if i < len(people) else None) or entry.receivers != expected:
            return result(False, f"the allowed receivers of entry {i} are wrong")
    if len(output.allowed) != len(people) or output.rule is not task.rule:
        return result(False, "allowed must list every person once, and rule must be the task's")
    return result(True, "the group is the seed's")


def checks_path(task):
    return f"santa/{task.rule.value}-{task.size}-{task.seed}.checks.json"


def checks_used(task, workspace):
    path = Path(workspace) / checks_path(task)
    if not path.is_file():
        return 0
    return json.loads(path.read_text(encoding="utf-8")).get("checks", 0)


def verify_check_output(check, output, workspace):
    if output.checks_left != MAX_CHECKS - checks_used(check.task, workspace):
        return result(False, "checks_left does not match the checks recorded in the workspace")
    people, excluded = rebuild_group(check.task)
    expected = broken_rules(people, excluded, check.task.rule.value, check.pairs)
    listed = [(p.kind.value, p.person) for p in output.problems]
    reported = set(listed)
    if len(listed) != len(reported) or reported != expected or output.valid != (not expected):
        return result(False, "the check does not report exactly the rules the assignment breaks", expected=describe(expected))
    return result(True, "the check is right", problems=len(expected))


def verify_pin_output(task, output):
    if task_problem(task):
        return result(False, task_problem(task))
    people, excluded = rebuild_group(task)
    total = count_valid(task)
    if output.group_sha256 != group_hash(people, excluded, task.rule.value):
        return result(False, "the pinned group is not the seed's")
    if output.count != total or output.feasible != (total > 0):
        return result(False, f"the pinned count is {output.count}; the verifier counts {total}")
    if output.feasible and broken_rules(people, excluded, task.rule.value, output.example):
        return result(False, "the pinned example breaks a rule")
    if not output.feasible and output.example:
        return result(False, "an impossible group has no example")
    return result(True, "the answer key agrees with the verifier", count=total)


def verify_task(arguments, output, reference, workspace):
    if task_problem(arguments):
        return result(False, task_problem(arguments))
    people, excluded = rebuild_group(arguments)
    rule = arguments.rule.value
    total = count_valid(arguments)
    if reference is None or verify_pin_output(arguments, reference)["valid"] is False:
        return result(False, "the pinned answer key does not match the group the seed gives")
    details = {
        "people": len(people),
        "rule": rule,
        "valid_assignments": total,
        "status": output.status.value,
        "checks_used": checks_used(arguments, workspace),
    }
    if output.status.value == "impossible":
        if total:
            return result(False, f"the group is possible: {total} valid assignments exist", score=0.0, **details)
        if output.pairs:
            return result(False, "an impossible answer must list no pairs", score=0.0, **details)
        return result(True, "correct: no valid assignment exists (the exhaustive count is 0)", **details)
    broken = broken_rules(people, excluded, rule, output.pairs)
    details["broken_rules"] = describe(broken)
    if broken:
        message = "the assignment breaks " + "; ".join(describe(broken)[:6])
        if not total:
            message += " (and the group is impossible: the answer was impossible)"
        return result(False, message, score=0.0, **details)
    return result(True, f"a valid assignment for all {len(people)} people", **details)
