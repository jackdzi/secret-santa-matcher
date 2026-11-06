"""A seeded generator built on sha256, so every instance is the same on every machine and Python.

The verifier keeps its own copy of this file (verifier/rng.py): it may not import `random`, and
it rebuilds each instance itself rather than trusting the tool that served it.
"""

import hashlib
import json


class Stream:
    """Deterministic numbers for one (namespace, key): draw n is sha256("namespace|key|n")."""

    def __init__(self, namespace, key):
        self.prefix = f"{namespace}|{key}|"
        self.count = 0

    def bits64(self):
        digest = hashlib.sha256(f"{self.prefix}{self.count}".encode()).digest()
        self.count += 1
        return int.from_bytes(digest[:8], "big")

    def below(self, n):
        """An integer in [0, n)."""
        if n <= 0:
            raise ValueError("below() needs n > 0")
        return self.bits64() % n

    def between(self, low, high):
        """An integer in [low, high], both included."""
        return low + self.below(high - low + 1)

    def chance(self, numerator, denominator):
        """True with probability numerator/denominator."""
        return self.below(denominator) < numerator

    def choice(self, items):
        return items[self.below(len(items))]

    def shuffled(self, items):
        items = list(items)
        for i in range(len(items) - 1, 0, -1):
            j = self.below(i + 1)
            items[i], items[j] = items[j], items[i]
        return items


def canonical_sha256(value):
    """sha256 of a JSON value written canonically: sorted keys, no spaces."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
