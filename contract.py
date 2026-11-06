"""Each tool's and task's typed input and output (see nanoagent.plugin.v0001.contract): declarations only."""

from dataclasses import dataclass
from enum import Enum
from typing import Annotated

from slimconfig import Output


class Tool(Enum):
    GET_GROUP = "get_group"
    CHECK_ASSIGNMENT = "check_assignment"
    PIN_FEASIBILITY = "pin_feasibility"


class Task(Enum):
    MATCH_GIFTS = "match-gifts"


class Rule(Enum):
    ANY = "any"
    SINGLE_CYCLE = "single-cycle"


class Reason(Enum):
    COUPLE = "couple"
    HOUSEHOLD = "household"
    LAST_YEAR = "last-year"
    REQUEST = "request"


class Status(Enum):
    ASSIGNED = "assigned"
    IMPOSSIBLE = "impossible"


class ProblemKind(Enum):
    UNKNOWN_PERSON = "unknown-person"
    GIVES_TWICE = "gives-twice"
    NEVER_GIVES = "never-gives"
    RECEIVES_TWICE = "receives-twice"
    NEVER_RECEIVES = "never-receives"
    SELF_GIFT = "self-gift"
    EXCLUDED = "excluded"
    NOT_ONE_CYCLE = "not-one-cycle"


PERSON = "A participant's name, exactly as get_group gives it"
TASK = "The task input, copied exactly as given"


@dataclass
class GroupInput(Output):
    seed: Annotated[int, "Which group: any integer from 0 to 1000000000; the same seed always gives the same group"]
    size: Annotated[int, "How many people take part, from 2 to 10"]
    rule: Annotated[
        Rule,
        "any: every person gives one gift and receives one; single-cycle: also, following giver to receiver from anyone"
        " visits everyone once before returning to them (one loop, no smaller loops)",
    ]


@dataclass
class Exclusion(Output):
    giver: Annotated[str, PERSON]
    receiver: Annotated[str, "Someone the giver may not give to"]
    reason: Annotated[Reason, "couple, household, last-year (the giver gave to them last year) or request"]


@dataclass
class Allowed(Output):
    giver: Annotated[str, PERSON]
    receivers: Annotated[list[str], "Everyone this giver may give to: not themselves and not excluded, in the people order"]


@dataclass
class GroupOutput(Output):
    people: Annotated[list[str], "Every participant's name"]
    rule: Annotated[Rule, "The task's rule"]
    exclusions: Annotated[list[Exclusion], "Every giver-to-receiver pair that is not allowed; a couple excludes both ways"]
    allowed: Annotated[list[Allowed], "For each person, in the people order, everyone they may give to"]


@dataclass
class Pair(Output):
    giver: Annotated[str, PERSON]
    receiver: Annotated[str, PERSON]


@dataclass
class CheckInput(Output):
    task: Annotated[GroupInput, TASK]
    pairs: Annotated[list[Pair], "A proposed assignment: one giver-to-receiver pair per person"]


@dataclass
class Problem(Output):
    kind: Annotated[ProblemKind, "Which rule the assignment breaks"]
    person: Annotated[str, "The person the problem is about (the giver for self-gift and excluded)"]
    detail: Annotated[str, "What is wrong, in words"]


@dataclass
class CheckOutput(Output):
    valid: Annotated[bool, "true when the assignment breaks no rule"]
    problems: Annotated[list[Problem], "Every rule the assignment breaks; empty when it is valid"]
    checks_left: Annotated[int, "How many more check_assignment calls this task allows (2 in all)"]


@dataclass
class AssignmentOutput(Output):
    status: Annotated[Status, "assigned: pairs is a valid assignment; impossible: no valid assignment exists"]
    pairs: Annotated[list[Pair], "The assignment, one pair per person; empty when the status is impossible"]


@dataclass
class PinOutput(Output):
    group_sha256: Annotated[str, "sha256 of the group (people, exclusions and rule) as canonical JSON"]
    feasible: Annotated[bool, "true when a valid assignment exists"]
    example: Annotated[list[Pair], "One valid assignment; empty when none exists"]
    count: Annotated[int, "How many valid assignments exist"]


TOOLS = {
    Tool.GET_GROUP: (GroupInput, GroupOutput),
    Tool.CHECK_ASSIGNMENT: (CheckInput, CheckOutput),
    Tool.PIN_FEASIBILITY: (GroupInput, PinOutput),
}
TASKS = {Task.MATCH_GIFTS: (GroupInput, AssignmentOutput)}
