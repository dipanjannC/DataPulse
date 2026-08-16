"""Multi-agent pipeline for DataPulse Text2SQL.

Six named agents process each natural-language question in a strict sequence,
streaming Server-Sent Events so the frontend can animate them in real time.

  LEXIS    — NL Interpreter    (parse intent, entities, filters)
  GRAPHOS  — KG Search Agent   (vector-search the Neo4j schema graph)
  SCOUT    — Schema Discovery  (map tables/columns/domains + confidence)
  FORGE    — SQL Writer        (draft the SQL query from schema context)
  SENTINEL — SQL Validator     (syntax, safety, table-existence checks)
  ORACLE   — Executor & NL     (run SQL, translate result to natural language)
"""
