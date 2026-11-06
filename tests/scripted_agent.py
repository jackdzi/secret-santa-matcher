"""A scripted stand-in for the agent: it follows the task's instructions with no model, so a whole
run can be replayed offline. It reads only what get_group returns."""

from __future__ import annotations


def assignment_from_group(people: list[str], allowed: dict[str, list[str]], rule: str) -> list[dict] | None:
    """Pairs for a valid assignment found by plain search over the allowed lists, or None when
    there is none."""
    if rule == "single-cycle":
        first = people[0]

        def chain(path: list[str]) -> list[str] | None:
            if len(path) == len(people):
                return path if first in allowed[path[-1]] else None
            for receiver in allowed[path[-1]]:
                if receiver not in path:
                    found = chain([*path, receiver])
                    if found:
                        return found
            return None

        loop = chain([first])
        if loop is None:
            return None
        return [{"giver": g, "receiver": loop[(i + 1) % len(loop)]} for i, g in enumerate(loop)]

    givers = sorted(people, key=lambda p: len(allowed[p]))

    def place(i: int, taken: dict[str, str]) -> dict[str, str] | None:
        if i == len(givers):
            return taken
        for receiver in allowed[givers[i]]:
            if receiver not in taken.values():
                found = place(i + 1, {**taken, givers[i]: receiver})
                if found:
                    return found
        return None

    chosen = place(0, {})
    return None if chosen is None else [{"giver": g, "receiver": chosen[g]} for g in people]
