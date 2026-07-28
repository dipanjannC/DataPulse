"""Step 6 — KG retriever (join planner).

Given a natural-language question:
1. Embed the question.
2. Soft domain routing — rank Domain nodes by vector similarity. No hard filter;
   the ranking boosts within-domain recall and groups the prompt, but columns
   from any domain remain eligible (cross-domain questions still work).
3. Seed tables — vector-search Column and Table nodes; pull a few extra column
   hits scoped to the top routed domains to lift recall where it matters.
4. Join-path expansion — walk shortest paths over :REFERENCES between the seed
   tables (undirected, bounded depth). This is where the graph earns its keep:
   starting from a dimension (e.g. customers) it reaches the fact tables that
   point *into* it, and it surfaces the exact join keys on every hop.
5. Assemble a schema-context dict: `tables` (unchanged shape, backward-compatible
   with the API/UI), plus `joins` (explicit join keys) and `domains` (routing).

Neo4j access is isolated in `SchemaGraph` so the orchestration and assembly are
unit-testable with a fake — no live Aura instance required.
"""
from __future__ import annotations

from neo4j import GraphDatabase

from src.embeddings.embed import embed_query

DEFAULT_TOP_K   = 10   # global column hits
DOMAIN_TOP_N    = 5    # domains ranked and returned to the caller
DOMAIN_ROUTE_N  = 2    # domains treated as "routed" for the recall boost
DOMAIN_SCOPED_K = 30   # column candidates pulled, then filtered to routed domains
TABLE_TOP_T     = 5    # table-level hits
MAX_SEEDS       = 8    # cap seed tables before join-path expansion
MAX_JOIN_HOPS   = 3    # shortest-path bound over :REFERENCES


# ── graph boundary — the only code that talks to Neo4j ──────────────────────────

class SchemaGraph:
    """Thin Neo4j boundary returning plain rows. Mock this in tests."""

    def __init__(self, driver) -> None:
        self._driver = driver

    def route_domains(self, q_vec: list[float], top_n: int) -> list[dict]:
        """Rows: {name, description, score}. Fakes must match this shape."""
        with self._driver.session() as s:
            return s.run(
                """
                CALL db.index.vector.queryNodes('domain_embedding', $n, $q)
                YIELD node, score
                RETURN node.name AS name, node.description AS description, score
                """,
                n=top_n, q=q_vec,
            ).data()

    def search_columns(
        self, q_vec: list[float], top_k: int, domains: list[str] | None = None
    ) -> list[dict]:
        """Rows: {table_name, domain, score}. Fakes must match this shape."""
        clause = "WHERE node.domain IN $domains" if domains else ""
        with self._driver.session() as s:
            return s.run(
                f"""
                CALL db.index.vector.queryNodes('column_embedding', $k, $q)
                YIELD node, score
                {clause}
                RETURN node.table_name AS table_name, node.domain AS domain, score
                """,
                k=top_k, q=q_vec, domains=domains or [],
            ).data()

    def search_tables(self, q_vec: list[float], top_t: int) -> list[dict]:
        """Rows: {table_name, domain, score}. Fakes must match this shape."""
        with self._driver.session() as s:
            return s.run(
                """
                CALL db.index.vector.queryNodes('table_embedding', $t, $q)
                YIELD node, score
                RETURN node.name AS table_name, node.domain AS domain, score
                """,
                t=top_t, q=q_vec,
            ).data()

    def join_paths(self, seeds: list[str], max_hops: int) -> list[dict]:
        """Rows: {tables: [str], edges: [{start, end, from_column, to_column}]}.

        Each edge is a stored REFERENCES relationship (child -> parent), so
        start/end are always child/parent regardless of traversal direction.
        Fakes must match this shape.
        """
        # Variable-length bounds cannot be parameterised in Cypher; max_hops is an
        # int constant we control, coerced here to keep it non-injectable.
        with self._driver.session() as s:
            return s.run(
                f"""
                UNWIND $seeds AS a_name
                UNWIND $seeds AS b_name
                WITH a_name, b_name WHERE a_name < b_name
                MATCH (a:Table {{name: a_name}}), (b:Table {{name: b_name}})
                MATCH p = shortestPath((a)-[:REFERENCES*1..{int(max_hops)}]-(b))
                RETURN [n IN nodes(p) | n.name] AS tables,
                       [r IN relationships(p) | {{
                           start:       startNode(r).name,
                           end:         endNode(r).name,
                           from_column: r.from_column,
                           to_column:   r.to_column
                       }}] AS edges
                """,
                seeds=seeds,
            ).data()

    def self_joins(self, tables: list[str]) -> list[dict]:
        """Rows: {name, from_column, to_column} — self-referential REFERENCES
        loops (e.g. employees.manager_id -> employees.employee_id) that pairwise
        shortest paths between distinct tables cannot surface. Fakes must match
        this shape."""
        with self._driver.session() as s:
            return s.run(
                """
                MATCH (t:Table)-[r:REFERENCES]->(t)
                WHERE t.name IN $tables
                RETURN t.name AS name, r.from_column AS from_column, r.to_column AS to_column
                """,
                tables=tables,
            ).data()

    def fetch_tables(self, tables: list[str]) -> list[dict]:
        """Rows: one per column — {table_name, table_desc, domain, col_name,
        dtype, col_desc, is_pk}. Fakes must match this shape."""
        with self._driver.session() as s:
            return s.run(
                """
                MATCH (t:Table)-[:HAS_COLUMN]->(c:Column)
                WHERE t.name IN $tables
                RETURN t.name        AS table_name,
                       t.description AS table_desc,
                       t.domain      AS domain,
                       c.name        AS col_name,
                       c.data_type   AS dtype,
                       c.description AS col_desc,
                       c.is_primary_key AS is_pk
                """,
                tables=tables,
            ).data()

    def fetch_metrics(self, tables: list[str]) -> list[dict]:
        """Rows: {name, expression, description} for canonical metrics whose
        referenced tables intersect the retrieved tables. Fakes must match this
        shape."""
        with self._driver.session() as s:
            return s.run(
                """
                MATCH (m:Metric)
                WHERE any(t IN m.tables WHERE t IN $tables)
                RETURN m.name AS name, m.expression AS expression, m.description AS description
                """,
                tables=tables,
            ).data()


# ── public API ──────────────────────────────────────────────────────────────

_GRAPH_CACHE: dict[tuple, SchemaGraph] = {}


def _get_graph(uri: str, user: str, password: str) -> SchemaGraph:
    key = (uri, user, password)
    graph = _GRAPH_CACHE.get(key)
    if graph is None:
        driver = GraphDatabase.driver(uri, auth=(user, password))
        graph = SchemaGraph(driver)
        _GRAPH_CACHE[key] = graph
    return graph


def retrieve_schema_context(
    question: str,
    uri: str,
    user: str,
    password: str,
    top_k: int = DEFAULT_TOP_K,
) -> dict:
    """
    Return {
        'tables': {table_name: {'description', 'domain', 'columns': [...]}},
        'joins':  [{'from_table', 'from_column', 'to_table', 'to_column'}, ...],
        'domains':[{'name', 'score'}, ...],   # soft routing, ranked
    }
    """
    q_vec = embed_query(question)
    graph = _get_graph(uri, user, password)
    return retrieve_context(graph, q_vec, top_k)


# ── orchestration (pure over a SchemaGraph-like boundary; unit-tested) ──────────

def retrieve_context(graph, q_vec: list[float], top_k: int = DEFAULT_TOP_K) -> dict:
    domains = graph.route_domains(q_vec, DOMAIN_TOP_N)
    routed  = [d["name"] for d in domains[:DOMAIN_ROUTE_N]]

    col_hits = list(graph.search_columns(q_vec, top_k))
    if routed:
        col_hits += graph.search_columns(q_vec, DOMAIN_SCOPED_K, domains=routed)
    table_hits = graph.search_tables(q_vec, TABLE_TOP_T)

    seeds = _seed_tables(col_hits, table_hits, MAX_SEEDS)

    paths = graph.join_paths(seeds, MAX_JOIN_HOPS) if len(seeds) > 1 else []
    all_tables, joins = _collect_paths(paths, seeds)

    if all_tables:
        for sj in graph.self_joins(all_tables):
            joins.append({
                "from_table":  sj["name"],
                "from_column": sj["from_column"],
                "to_table":    sj["name"],
                "to_column":   sj["to_column"],
            })

    rows    = graph.fetch_tables(all_tables) if all_tables else []
    metrics = graph.fetch_metrics(all_tables) if all_tables else []
    return _build_context(rows, joins, domains, metrics)


def _seed_tables(col_hits: list[dict], table_hits: list[dict], max_seeds: int) -> list[str]:
    """Rank candidate tables by their best vector score; keep the top few."""
    best: dict[str, float] = {}
    for r in (*col_hits, *table_hits):
        name  = r["table_name"]
        score = r.get("score") or 0.0
        if name not in best or score > best[name]:
            best[name] = score
    ranked = sorted(best, key=lambda n: best[n], reverse=True)
    return ranked[:max_seeds]


def _collect_paths(paths: list[dict], seeds: list[str]) -> tuple[list[str], list[dict]]:
    """Union the tables on every join path with the seeds; dedupe join edges."""
    tables = list(seeds)
    joins: list[dict] = []
    seen: set[tuple] = set()
    for p in paths:
        for t in p.get("tables", []):
            if t not in tables:
                tables.append(t)
        for e in p.get("edges", []):
            key = (e["start"], e["from_column"], e["end"], e["to_column"])
            if key not in seen:
                seen.add(key)
                joins.append({
                    "from_table":  e["start"],
                    "from_column": e["from_column"],
                    "to_table":    e["end"],
                    "to_column":   e["to_column"],
                })
    return tables, joins


def _build_context(
    rows: list[dict],
    joins: list[dict],
    domains: list[dict],
    metrics: list[dict] | None = None,
) -> dict:
    tables: dict[str, dict] = {}
    for r in rows:
        tname = r["table_name"]
        if tname not in tables:
            tables[tname] = {
                "description": r.get("table_desc") or "",
                "domain":      r.get("domain") or "",
                "columns":     [],
            }
        tables[tname]["columns"].append({
            "name":        r["col_name"],
            "type":        r["dtype"],
            "description": r["col_desc"],
            "is_pk":       bool(r.get("is_pk")),
        })

    present = set(tables)
    joins = [j for j in joins if j["from_table"] in present and j["to_table"] in present]

    return {
        "tables":  tables,
        "joins":   joins,
        "domains": [{"name": d["name"], "score": d.get("score")} for d in domains],
        "metrics": [
            {"name": m["name"], "expression": m["expression"], "description": m.get("description", "")}
            for m in (metrics or [])
        ],
    }
