"""Step 8 — Streamlit UI.

Run:
    uv run streamlit run text2sql/app/app.py
"""
from __future__ import annotations

import os
import sys
import sqlite3
from pathlib import Path

# Ensure project root is on sys.path when run via `streamlit run`
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

from text2sql.knowledge_graph.retriever import retrieve_schema_context
from text2sql.sql_gen.generator import generate_sql

DB_PATH = Path(__file__).parent.parent / "db" / "sales.db"

# ── page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="DataPulse Text2SQL",
    page_icon="⚡",
    layout="wide",
)

st.title("⚡ DataPulse — Text to SQL")
st.caption(
    "Ask a question in plain English. "
    "Relevant tables and columns are retrieved from the Knowledge Graph, "
    "then an LLM generates and validates the SQL for you."
)

# ── sidebar: credentials ──────────────────────────────────────────────────────
with st.sidebar:
    st.header("Configuration")
    groq_key    = st.text_input("Groq API Key",    value=os.getenv("GROQ_API_KEY",    ""), type="password")
    neo4j_uri   = st.text_input("Neo4j URI",        value=os.getenv("NEO4J_URI",       ""))
    neo4j_user  = st.text_input("Neo4j Username",   value=os.getenv("NEO4J_USERNAME",  "neo4j"))
    neo4j_pass  = st.text_input("Neo4j Password",   value=os.getenv("NEO4J_PASSWORD",  ""), type="password")
    top_k       = st.slider("Top-K columns to retrieve", min_value=5, max_value=25, value=10)

    st.divider()
    st.markdown("**Example questions**")
    examples = [
        "Top 5 products by total revenue in 2024",
        "How many orders were placed per channel last year?",
        "Which customers have Gold or Platinum loyalty tier?",
        "Average order value by region",
        "Products with less than 10 units in stock",
    ]
    for ex in examples:
        if st.button(ex, use_container_width=True):
            st.session_state["question_input"] = ex

# ── main input ────────────────────────────────────────────────────────────────
st.divider()
question = st.text_input(
    "Ask a question about your sales data",
    placeholder="e.g. What are the top 5 products by total revenue in 2024?",
    key="question_input",
)

run_clicked = st.button("Run Query", type="primary", disabled=not question.strip())

# ── execution ─────────────────────────────────────────────────────────────────
if run_clicked:
    missing = [
        name for name, val in [
            ("Groq API Key",  groq_key),
            ("Neo4j URI",     neo4j_uri),
            ("Neo4j Password", neo4j_pass),
        ]
        if not val.strip()
    ]
    if missing:
        st.error(f"Missing configuration: {', '.join(missing)}")
        st.stop()

    if not DB_PATH.exists():
        st.error(
            f"Database not found at `{DB_PATH}`.  "
            "Run `uv run python text2sql/pipeline.py` first to generate data and build the KG."
        )
        st.stop()

    # Step 1 — KG retrieval
    with st.spinner("Retrieving schema from Knowledge Graph…"):
        try:
            context = retrieve_schema_context(
                question, neo4j_uri, neo4j_user, neo4j_pass, top_k
            )
        except Exception as exc:
            st.error(f"Knowledge Graph retrieval failed: {exc}")
            st.stop()

    # Step 2 — SQL generation + validation
    with st.spinner("Generating SQL with Groq LLM…"):
        db_conn = sqlite3.connect(DB_PATH)
        result  = generate_sql(question, context, groq_key, db_conn=db_conn)

    # ── display ───────────────────────────────────────────────────────────────
    left, right = st.columns([1, 2], gap="large")

    with left:
        st.subheader("Retrieved Schema Context")
        if not context["tables"]:
            st.warning("No relevant tables found. Try rephrasing your question.")
        for tname, info in context["tables"].items():
            with st.expander(f"**{tname}** — {info['description']}", expanded=True):
                st.dataframe(
                    pd.DataFrame(info["columns"])[["name", "type", "description"]],
                    use_container_width=True,
                    hide_index=True,
                )

    with right:
        st.subheader("Generated SQL")
        st.code(result["sql"], language="sql")

        if result["attempts"] > 1:
            st.caption(f"Validated after {result['attempts']} attempt(s).")
        if not result["success"]:
            st.warning(f"SQL validation failed after {MAX_RETRIES} attempts: {result['error']}")

        st.subheader("Query Results")
        try:
            df = pd.read_sql_query(result["sql"], db_conn)
            if df.empty:
                st.info("Query returned no rows.")
            else:
                st.dataframe(df, use_container_width=True)
                st.caption(f"{len(df):,} row(s) returned.")
        except Exception as exc:
            st.error(f"Query execution failed: {exc}")
        finally:
            db_conn.close()


# reference for MAX_RETRIES in warning message
try:
    from text2sql.sql_gen.generator import MAX_RETRIES
except ImportError:
    MAX_RETRIES = 3
