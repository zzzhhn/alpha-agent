"""Phase C: expression-tree genetics for the GA factor miner.

A cheap, non-LLM candidate generator: mutate/crossover WorldQuant-style factor
expressions over the same DSL the LLM proposer and validators use. This module
is PURE tree manipulation (no DB, no kernel) so the genetic operators can be
unit-tested in isolation; ga_search.py adds the panel-backed fitness + loop.

Tree format matches core.factor_ast.expression_to_tree, so a parsed seed factor
drops straight in:
    {"type": "operator", "name": str, "args": [tree, ...]}
    {"type": "operand",  "name": str}                 # a field leaf
    {"type": "literal",  "value": float|int}          # a window / param constant

Genetic operators only ever splice at 'expr' argument slots, and only swap
operators that share an argument-kind signature, so offspring stay grammatically
valid (a validate_expression pass in ga_search is the final backstop that also
drops the degenerate subtract(x,x) / divide(x,x) forms the grammar rejects)."""
from __future__ import annotations

import random

# ── argument-kind vocabulary ────────────────────────────────────────────
# Only 'expr' slots are recursively grown / spliced; 'window' and 'param' are
# numeric literals; 'group' is a categorical field. Curated subset of the full
# 43-op catalog — enough for rich search, chosen so every arg kind is
# unambiguous (see data/wq_catalog/operators_augmented.json for signatures).
EXPR, WINDOW, PARAM, GROUP = "expr", "window", "param", "group"

GA_OPS: dict[str, tuple[str, ...]] = {
    # unary transforms
    "rank": (EXPR,), "zscore": (EXPR,), "normalize": (EXPR,), "scale": (EXPR,),
    "sign": (EXPR,), "log": (EXPR,), "abs": (EXPR,), "inverse": (EXPR,),
    "sqrt": (EXPR,),
    # binary arithmetic
    "add": (EXPR, EXPR), "subtract": (EXPR, EXPR), "multiply": (EXPR, EXPR),
    "divide": (EXPR, EXPR), "max": (EXPR, EXPR), "min": (EXPR, EXPR),
    # power / winsorize take a numeric param, not a sub-expression
    "power": (EXPR, PARAM), "signed_power": (EXPR, PARAM),
    "winsorize": (EXPR, PARAM),
    # time-series (window literal last)
    "ts_mean": (EXPR, WINDOW), "ts_std_dev": (EXPR, WINDOW),
    "ts_sum": (EXPR, WINDOW), "ts_delta": (EXPR, WINDOW),
    "ts_delay": (EXPR, WINDOW), "ts_min": (EXPR, WINDOW),
    "ts_max": (EXPR, WINDOW), "ts_rank": (EXPR, WINDOW),
    "ts_zscore": (EXPR, WINDOW), "ts_decay_linear": (EXPR, WINDOW),
    # two-series time-series
    "ts_corr": (EXPR, EXPR, WINDOW), "ts_regression": (EXPR, EXPR, WINDOW),
    # group (cross-section within a categorical bucket)
    "group_rank": (EXPR, GROUP), "group_zscore": (EXPR, GROUP),
    "group_neutralize": (EXPR, GROUP),
}

# Ops safe to wrap an arbitrary sub-expression in (structural mutation). All
# take the sub-expr as arg 0; any remaining args are filled per their kind.
UNARY_WRAP_OPS = (
    "rank", "zscore", "normalize", "scale",
    "ts_mean", "ts_zscore", "ts_rank",
)

# Numeric field leaves (fill an 'expr' operand). Categorical fields live in
# GROUP_FIELDS and only ever fill a 'group' slot.
NUMERIC_FIELDS = (
    "close", "open", "high", "low", "volume", "returns", "vwap",
    "cap", "adv20", "adv60", "dollar_volume",
    "revenue", "net_income_adjusted", "ebitda", "eps", "equity", "assets",
    "free_cash_flow", "gross_profit",
)
GROUP_FIELDS = ("sector", "industry", "subindustry", "exchange")
WINDOWS = (5, 10, 20, 40, 60, 120)
PARAMS = (2, 3, 4)

# Ops grouped by arg-kind signature, so an operator can be swapped only for one
# whose arguments it already satisfies (offspring stays valid without regrowth).
OPS_BY_SIG: dict[tuple[str, ...], list[str]] = {}
for _n, _sig in GA_OPS.items():
    OPS_BY_SIG.setdefault(_sig, []).append(_n)


# ── tree <-> expression ──────────────────────────────────────────────────
def tree_to_expression(tree: dict) -> str:
    """Serialize a tree back to a DSL string. Integer-valued literals print
    without a trailing .0 so windows read as `20`, not `20.0`."""
    t = tree["type"]
    if t == "operand":
        return tree["name"]
    if t == "literal":
        v = tree["value"]
        return str(int(v)) if float(v).is_integer() else repr(v)
    if t == "operator":
        inner = ", ".join(tree_to_expression(a) for a in tree["args"])
        return f'{tree["name"]}({inner})'
    raise ValueError(f"bad tree node: {tree!r}")


def used_operators(tree: dict) -> list[str]:
    """Distinct operator names, in first-seen order — for validate_expression's
    declared-ops argument (which must equal the ops actually used)."""
    seen: dict[str, None] = {}

    def walk(n: dict) -> None:
        if n["type"] == "operator":
            seen.setdefault(n["name"], None)
            for a in n["args"]:
                walk(a)

    walk(tree)
    return list(seen)


def tree_depth(tree: dict) -> int:
    """Operator-nesting depth. A leaf field/literal is depth 0."""
    if tree["type"] != "operator":
        return 0
    return 1 + max((tree_depth(a) for a in tree["args"]), default=0)


# ── random generation ────────────────────────────────────────────────────
def _leaf(rng: random.Random) -> dict:
    return {"type": "operand", "name": rng.choice(NUMERIC_FIELDS)}


def _arg(rng: random.Random, kind: str, depth: int) -> dict:
    if kind == WINDOW:
        return {"type": "literal", "value": rng.choice(WINDOWS)}
    if kind == PARAM:
        return {"type": "literal", "value": rng.choice(PARAMS)}
    if kind == GROUP:
        return {"type": "operand", "name": rng.choice(GROUP_FIELDS)}
    return random_tree(rng, depth)  # EXPR


def random_tree(rng: random.Random, depth: int) -> dict:
    """Grow a random valid tree of at most `depth` operator levels. A leaf field
    is returned once depth is exhausted or on a coin-flip (keeps trees shallow)."""
    if depth <= 0 or rng.random() < 0.35:
        return _leaf(rng)
    op = rng.choice(list(GA_OPS))
    return {
        "type": "operator",
        "name": op,
        "args": [_arg(rng, k, depth - 1) for k in GA_OPS[op]],
    }


def random_population(rng: random.Random, size: int, depth: int = 3) -> list[dict]:
    return [random_tree(rng, depth) for _ in range(size)]


# ── addressing 'expr' slots (the only splice / mutate targets) ────────────
def expr_paths(tree: dict) -> list[tuple[int, ...]]:
    """Paths (tuples of arg indices from the root) to every node sitting in an
    'expr' slot — operators and field operands, never a window/param/group. The
    root is always an expr slot."""
    out: list[tuple[int, ...]] = []

    def walk(n: dict, path: tuple[int, ...]) -> None:
        out.append(path)
        if n["type"] == "operator":
            for i, kind in enumerate(GA_OPS.get(n["name"], ())):
                if kind == EXPR:
                    walk(n["args"][i], path + (i,))

    walk(tree, ())
    return out


def at(tree: dict, path: tuple[int, ...]) -> dict:
    for i in path:
        tree = tree["args"][i]
    return tree


def replace_at(tree: dict, path: tuple[int, ...], sub: dict) -> dict:
    """Return a NEW tree with the node at `path` replaced by `sub` (immutable —
    the input tree is never mutated)."""
    if not path:
        return sub
    i = path[0]
    new_args = list(tree["args"])
    new_args[i] = replace_at(tree["args"][i], path[1:], sub)
    return {**tree, "args": new_args}


# ── genetic operators ─────────────────────────────────────────────────────
def crossover(rng: random.Random, a: dict, b: dict) -> dict:
    """Replace a random expr-subtree of `a` with a random expr-subtree of `b`.
    Both splice points are expr slots, so the result is grammatically valid."""
    pa = rng.choice(expr_paths(a))
    pb = rng.choice(expr_paths(b))
    return replace_at(a, pa, at(b, pb))


def _mutate_operand(rng: random.Random, tree: dict) -> dict | None:
    paths = [p for p in expr_paths(tree) if at(tree, p)["type"] == "operand"]
    if not paths:
        return None
    p = rng.choice(paths)
    cur = at(tree, p)["name"]
    # An expr-slot operand is always numeric (group operands live off expr slots).
    choices = [f for f in NUMERIC_FIELDS if f != cur]
    return replace_at(tree, p, {"type": "operand", "name": rng.choice(choices)})


def _mutate_operator(rng: random.Random, tree: dict) -> dict | None:
    paths = [p for p in expr_paths(tree) if at(tree, p)["type"] == "operator"]
    if not paths:
        return None
    p = rng.choice(paths)
    node = at(tree, p)
    alts = [o for o in OPS_BY_SIG[GA_OPS[node["name"]]] if o != node["name"]]
    if not alts:
        return None
    return replace_at(tree, p, {**node, "name": rng.choice(alts)})


def _mutate_literal(rng: random.Random, tree: dict) -> dict | None:
    targets: list[tuple[tuple[int, ...], int, str]] = []
    for p in expr_paths(tree):
        node = at(tree, p)
        if node["type"] == "operator":
            for i, k in enumerate(GA_OPS.get(node["name"], ())):
                if k in (WINDOW, PARAM):
                    targets.append((p, i, k))
    if not targets:
        return None
    p, i, k = rng.choice(targets)
    node = at(tree, p)
    pool = WINDOWS if k == WINDOW else PARAMS
    cur = node["args"][i]["value"]
    choices = [v for v in pool if v != cur] or list(pool)
    new_args = list(node["args"])
    new_args[i] = {"type": "literal", "value": rng.choice(choices)}
    return replace_at(tree, p, {**node, "args": new_args})


def _mutate_wrap(rng: random.Random, tree: dict) -> dict | None:
    p = rng.choice(expr_paths(tree))
    sub = at(tree, p)
    op = rng.choice(UNARY_WRAP_OPS)
    args = [sub] + [_arg(rng, k, 1) for k in GA_OPS[op][1:]]
    return replace_at(tree, p, {"type": "operator", "name": op, "args": args})


def _mutate_subtree(rng: random.Random, tree: dict) -> dict | None:
    p = rng.choice(expr_paths(tree))
    return replace_at(tree, p, random_tree(rng, 2))


_MUTATORS = (
    _mutate_operand,
    _mutate_operator,
    _mutate_literal,
    _mutate_wrap,
    _mutate_subtree,
)


def mutate(rng: random.Random, tree: dict) -> dict:
    """Apply one randomly-chosen mutation. Tries kinds in a shuffled order and
    takes the first that applies (some don't fit every tree, e.g. a bare leaf
    has no operator to swap), so a mutation always happens where possible."""
    order = list(_MUTATORS)
    rng.shuffle(order)
    for m in order:
        out = m(rng, tree)
        if out is not None:
            return out
    return tree
