"""Tests for the KG retriever (join-planner orchestration + assembly).

These drive the pure seam only (`retrieve_context` and the module-level helpers)
against a fake SchemaGraph. The Cypher inside the real `SchemaGraph` is NOT
exercised here — it is verified by the post-rebuild acceptance checks in the
handoff. The fake's canned rows deliberately mirror the RETURN-shape docstrings
on each SchemaGraph method so the two cannot silently drift.
"""
from __future__ import annotations

from text2sql.knowledge_graph.retriever import (
    MAX_SEEDS,
    _build_context,
    _collect_paths,
    _seed_tables,
    retrieve_context,
)

Q = [0.1, 0.2, 0.3, 0.4]  # dummy query vector; the fake ignores it


# ── fake boundary ───────────────────────────────────────────────────────────

class _FakeSchemaGraph:
    """Duck-typed stand-in for SchemaGraph. Returns canned, shape-matched rows."""

    def __init__(self, *, domains=None, columns=None, tables=None, paths=None,
                 catalog=None, self_ref=None, metrics=None):
        self._domains  = domains or []
        self._columns  = columns or []
        self._tables   = tables or []
        self._paths    = paths or []
        self._catalog  = catalog or {}   # {table: {"desc","domain","columns":[(n,t,d,pk)]}}
        self._self_ref = self_ref or []  # [{"name","from_column","to_column"}]
        self._metrics  = metrics or []   # [{"name","expression","description","tables"}]
        self.calls: list[tuple] = []

    def route_domains(self, q_vec, top_n):
        self.calls.append(("route_domains", top_n))
        return self._domains[:top_n]

    def search_columns(self, q_vec, top_k, domains=None):
        self.calls.append(("search_columns", top_k, tuple(domains) if domains else None))
        rows = self._columns
        if domains:
            rows = [r for r in rows if r["domain"] in domains]
        return rows[:top_k]

    def search_tables(self, q_vec, top_t):
        self.calls.append(("search_tables", top_t))
        return self._tables[:top_t]

    def join_paths(self, seeds, max_hops):
        self.calls.append(("join_paths", tuple(seeds), max_hops))
        seedset = set(seeds)
        # mirror the Cypher WHERE: both endpoints must be seeds
        return [p for p in self._paths
                if {p["tables"][0], p["tables"][-1]} <= seedset]

    def self_joins(self, tables):
        self.calls.append(("self_joins", tuple(sorted(tables))))
        return [r for r in self._self_ref if r["name"] in set(tables)]

    def fetch_metrics(self, tables):
        self.calls.append(("fetch_metrics", tuple(sorted(tables))))
        seen = set(tables)
        return [m for m in self._metrics if seen & set(m.get("tables", []))]

    def fetch_tables(self, tables):
        self.calls.append(("fetch_tables", tuple(sorted(tables))))
        rows = []
        for t in tables:
            spec = self._catalog.get(t)
            if not spec:
                continue
            for (name, dtype, desc, pk) in spec["columns"]:
                rows.append({
                    "table_name": t,
                    "table_desc": spec["desc"],
                    "domain":     spec["domain"],
                    "col_name":   name,
                    "dtype":      dtype,
                    "col_desc":   desc,
                    "is_pk":      pk,
                })
        return rows


def _called(fake, method) -> bool:
    return any(c[0] == method for c in fake.calls)


# ── the headline: dimension -> fact reachability (the bug this whole change fixes)

def test_dimension_question_reaches_fact_tables_via_join_path():
    """'total revenue by customer loyalty tier' seeds customers + order_items;
    orders is not a vector hit but must be pulled in as a join connector, with
    the exact join keys surfaced. This is exactly what the old outgoing-only,
    one-hop retriever could not do."""
    fake = _FakeSchemaGraph(
        domains=[
            {"name": "Sales",     "description": "sales ops", "score": 0.91},
            {"name": "Marketing", "description": "mkt ops",   "score": 0.28},
        ],
        columns=[
            {"table_name": "customers",   "domain": "Sales", "score": 0.82},
            {"table_name": "order_items", "domain": "Sales", "score": 0.80},
        ],
        tables=[],  # note: `orders` is NOT surfaced by vector search
        paths=[{
            "tables": ["customers", "orders", "order_items"],
            "edges": [
                {"start": "orders",      "end": "customers", "from_column": "customer_id", "to_column": "customer_id"},
                {"start": "order_items", "end": "orders",    "from_column": "order_id",    "to_column": "order_id"},
            ],
        }],
        catalog={
            "customers":   {"desc": "customer master", "domain": "Sales",
                            "columns": [("customer_id", "INTEGER", "id", True), ("loyalty_tier", "TEXT", "tier", False)]},
            "orders":      {"desc": "order headers", "domain": "Sales",
                            "columns": [("order_id", "INTEGER", "id", True), ("customer_id", "INTEGER", "fk", False)]},
            "order_items": {"desc": "line items", "domain": "Sales",
                            "columns": [("order_id", "INTEGER", "fk", False), ("line_total", "REAL", "amount", False)]},
        },
    )

    ctx = retrieve_context(fake, Q, top_k=10)

    # the connector table the old retriever would have missed:
    assert "orders" in ctx["tables"]
    assert set(ctx["tables"]) == {"customers", "orders", "order_items"}

    # exact join keys reach the caller as explicit edges
    pairs = {(j["from_table"], j["from_column"], j["to_table"], j["to_column"]) for j in ctx["joins"]}
    assert ("orders", "customer_id", "customers", "customer_id") in pairs
    assert ("order_items", "order_id", "orders", "order_id") in pairs

    # soft routing ranked Sales first, and a join-path query actually ran
    assert ctx["domains"][0]["name"] == "Sales"
    assert _called(fake, "join_paths")


def test_self_referential_join_is_surfaced():
    """'employees and their managers' — the manager_id self-loop is not on any
    pairwise path, so it must be pulled in via self_joins and reach the caller."""
    fake = _FakeSchemaGraph(
        domains=[{"name": "HR", "description": "hr", "score": 0.8}],
        columns=[
            {"table_name": "employees", "domain": "HR", "score": 0.9},
            {"table_name": "positions", "domain": "HR", "score": 0.6},
        ],
        tables=[],
        paths=[{
            "tables": ["employees", "positions"],
            "edges": [{"start": "employees", "end": "positions",
                       "from_column": "position_id", "to_column": "position_id"}],
        }],
        self_ref=[{"name": "employees", "from_column": "manager_id", "to_column": "employee_id"}],
        catalog={
            "employees": {"desc": "emp", "domain": "HR", "columns": [
                ("employee_id", "INTEGER", "id", True),
                ("manager_id", "INTEGER", "mgr", False),
                ("position_id", "INTEGER", "fk", False)]},
            "positions": {"desc": "pos", "domain": "HR", "columns": [
                ("position_id", "INTEGER", "id", True)]},
        },
    )

    ctx = retrieve_context(fake, Q, top_k=10)

    pairs = {(j["from_table"], j["from_column"], j["to_table"], j["to_column"]) for j in ctx["joins"]}
    assert ("employees", "manager_id", "employees", "employee_id") in pairs


def test_canonical_metric_surfaces_when_its_table_is_retrieved():
    """The 'total revenue' metric must reach the caller whenever order_items is
    retrieved, so the LLM is told the canonical expression instead of guessing
    among invoices.amount / achieved_amount / revenue_attributed."""
    fake = _FakeSchemaGraph(
        domains=[{"name": "Sales", "description": "s", "score": 0.9}],
        columns=[{"table_name": "order_items", "domain": "Sales", "score": 0.8}],
        tables=[],
        paths=[],
        metrics=[{"name": "total revenue", "expression": "SUM(order_items.line_total)",
                  "description": "canonical revenue", "tables": ["order_items"]}],
        catalog={"order_items": {"desc": "li", "domain": "Sales",
                                 "columns": [("line_total", "REAL", "amt", False)]}},
    )

    ctx = retrieve_context(fake, Q, top_k=10)

    assert [m["name"] for m in ctx["metrics"]] == ["total revenue"]
    assert ctx["metrics"][0]["expression"] == "SUM(order_items.line_total)"


def test_single_seed_skips_join_path_expansion():
    fake = _FakeSchemaGraph(
        domains=[{"name": "Sales", "description": "d", "score": 0.9}],
        columns=[{"table_name": "products", "domain": "Sales", "score": 0.7}],
        tables=[],
        paths=[],
        catalog={"products": {"desc": "catalog", "domain": "Sales",
                              "columns": [("product_id", "INTEGER", "id", True)]}},
    )

    ctx = retrieve_context(fake, Q, top_k=10)

    assert set(ctx["tables"]) == {"products"}
    assert ctx["joins"] == []
    assert not _called(fake, "join_paths")  # never queried for a single seed


# ── seed selection ────────────────────────────────────────────────────────────

def test_seed_tables_ranks_by_best_score_and_caps():
    col_hits = [{"table_name": f"t{i}", "score": 0.90 + i / 100} for i in range(10)]  # t0..t9 ascending
    seeds = _seed_tables(col_hits, [], MAX_SEEDS)
    assert len(seeds) == MAX_SEEDS
    assert seeds[0] == "t9"                 # highest score first
    assert "t0" not in seeds and "t1" not in seeds  # two lowest dropped by the cap


def test_seed_tables_dedupes_keeping_best_score():
    col_hits   = [{"table_name": "orders", "score": 0.4}]
    table_hits = [{"table_name": "orders", "score": 0.95}]
    seeds = _seed_tables(col_hits, table_hits, MAX_SEEDS)
    assert seeds == ["orders"]


# ── path collection ─────────────────────────────────────────────────────────

def test_collect_paths_unions_tables_and_dedupes_edges():
    seeds = ["a", "c"]
    paths = [
        {"tables": ["a", "b", "c"], "edges": [
            {"start": "a", "end": "b", "from_column": "x", "to_column": "y"},
            {"start": "b", "end": "c", "from_column": "p", "to_column": "q"},
        ]},
        {"tables": ["a", "b"], "edges": [   # duplicate a->b edge must not double up
            {"start": "a", "end": "b", "from_column": "x", "to_column": "y"},
        ]},
    ]
    tables, joins = _collect_paths(paths, seeds)
    assert set(tables) == {"a", "b", "c"}
    assert len(joins) == 2


# ── context assembly ──────────────────────────────────────────────────────────

def test_build_context_shape_and_drops_dangling_joins():
    rows = [
        {"table_name": "orders", "table_desc": "hdr", "domain": "Sales",
         "col_name": "order_id", "dtype": "INTEGER", "col_desc": "id", "is_pk": True},
    ]
    joins = [
        {"from_table": "orders", "from_column": "customer_id", "to_table": "customers", "to_column": "customer_id"},
    ]
    domains = [{"name": "Sales", "score": 0.9}]

    ctx = _build_context(rows, joins, domains)

    assert ctx["tables"]["orders"]["domain"] == "Sales"
    assert ctx["tables"]["orders"]["columns"][0] == {
        "name": "order_id", "type": "INTEGER", "description": "id", "is_pk": True,
    }
    # customers was not fetched, so the join referencing it is dropped
    assert ctx["joins"] == []
    assert ctx["domains"] == [{"name": "Sales", "score": 0.9}]
    # metrics key is always present (additive contract), empty when none given
    assert ctx["metrics"] == []
