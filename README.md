# Secret Santa Matcher

A `nanoagent.plugin/v0001` plugin. Its task, `match-gifts`, gives an agent a
gift-exchange group of 2 to 10 people with exclusions (couples, households,
last year's pairs and requests) and a rule, and asks for an assignment: each
person gives one gift and receives one, nobody draws themselves or someone
they are excluded from, and under `single-cycle` the gifts form one loop
through everyone. About a fifth of groups, at every size, have no valid assignment, and
then the right answer is `impossible`. Any valid assignment passes; the
verifier proves an `impossible` answer by counting every assignment.

## Tools

| Tool | Does | Code |
|---|---|---|
| `get_group` | The task's people, every excluded giver-to-receiver pair with its reason, and each person's allowed receivers | `src/plugin/santa.py` |
| `check_assignment` | Lists every rule a proposed assignment breaks (unknown person, gives twice, never gives, receives twice, never receives, self-gift, excluded, not one loop); it never proposes an assignment | `src/plugin/santa.py` |
| `pin_feasibility` | The answer key: the group's sha256, whether a valid assignment exists, one example and how many there are | `src/plugin/santa.py` |

### Tasks

| Task | Does | Runner |
|---|---|---|
| `match-gifts` | Assigns everyone a receiver under the exclusions and the rule, or answers that no assignment exists | `agent`, with `get_group` and `check_assignment`; reference `pin_feasibility` |

## The task

Input: `seed` (0 to 1,000,000,000), `size` (2 to 10) and `rule` (`any` or
`single-cycle`). The agent calls `get_group`, proposes an assignment and
checks it with `check_assignment`, then submits
`{status: assigned, pairs}` or `{status: impossible, pairs: []}`.
`check_assignment` allows 2 checks per task, counted in the workspace
(`santa/<rule>-<size>-<seed>.checks.json`), and refuses a third: it gives
feedback, but the agent cannot find an assignment by trial and error.

## Ground truth and verification

The group is drawn by a sha256-based generator (`src/plugin/rng.py`), never
`random`, so a seed gives the same group on every machine. The seed first
decides whether its group is possible (4 in 5) or impossible (1 in 5), then
exclusions are drawn from successive streams until the group is that kind.
So about 20% of groups are impossible at every size, from 2 to 10, and an
agent that always answers `impossible` is right only about a fifth of the
time. Impossible groups come from couples, households and last year's pairs,
or from requests that leave k + 1 givers only k possible receivers.

`verify_task` (in `verifier/santa.py`):

1. Rebuilds the group from the seed with its own copy of the generator, and
   checks the pinned answer key (its sha256, its count and its example).
2. Counts every valid assignment on its own, by bottom-up dynamic programming
   over sets of people: the permanent of the allowed matrix for `any`, and
   the loops through everyone for `single-cycle`. The answer key's solver
   backtracks instead; the two agree on 2,000 groups in the tests.
3. For `impossible`: valid only when that count is 0 (an exhaustive proof)
   and no pairs are listed.
4. For `assigned`: lists every broken rule; valid only when there is none.

The verdict is all or nothing (score 1 or 0) and names every broken rule.
`verify_input` refuses a seed or size out of range; `verify_output` checks
each tool's output against the rebuilt group, including that
`check_assignment` reports exactly the broken rules, once each.

## Layout

```text
.
├── nanoagent.yaml   # manifest: id, runtime, permissions (no network), tools, task
├── contract.py      # each tool's and task's typed input and output
├── README.md
├── LICENSE
├── pyproject.toml
├── uv.lock
├── .gitignore
├── .env             # environment variable names needed (none)
├── src/plugin/      # the MCP server (__main__.py), the generator (rng.py) and the tools (santa.py)
├── tests/           # the verifier's tests, tool tests, a 2,000-group agreement test, an MCP smoke
│                    #   test, and a scripted no-model agent (scripted_agent.py)
├── ui/              # renderers.js and renderers.css: outputs drawn from their JSON Schema
├── product/         # the product page: product.yaml and icon.svg
└── verifier/        # the deterministic verifier: santa.py, its generator copy rng.py, checks.py
```

## Develop and run

```bash
uv sync --extra dev
uv run pytest
uv run ruff check .
```

No network and no data files: every group comes from its seed. NanoAgent
passes the folder the plugin may write to as `NANOAGENT_WORKSPACE`.
