"""Centralized prompt templates. All prompts use explicit JSON output formats
so agent outputs are deterministic and parseable."""

# ---------------------------------------------------------------------------
# RAPTOR — cluster summarization
# ---------------------------------------------------------------------------

CLUSTER_SUMMARIZER = """You are a precise document analyst. Summarize the following text excerpts \
into a coherent, dense paragraph of approximately 200-300 words.

Rules:
- Preserve all specific numbers, dates, names, and facts
- Do NOT add information not present in the excerpts
- Write in third person, present tense
- Output ONLY the summary — no preamble, no labels

Text excerpts:
{text}

Summary:"""


# ---------------------------------------------------------------------------
# Agent 1 — Query Intent
# ---------------------------------------------------------------------------

INTENT_CLASSIFICATION = """You are a query classifier for a document QA system.

Classify the user query into exactly one intent type and decompose if needed.

Intent types:
- factual_lookup: Single fact retrieval ("What was revenue in 2024?")
- comparison: Comparing two or more things/periods ("How did revenue change year-over-year?")
- multi_hop: Requires combining info from multiple sections ("Did profit margin improve as headcount grew?")
- tabular_aggregation: Requires summing/averaging table data ("Total employees across all regions")
- summarization: High-level overview ("Summarize the risk factors")

Respond with valid JSON only — no markdown, no explanation:
{{
  "intent_type": "<one of the five types>",
  "sub_queries": ["<sub-query 1>", "<sub-query 2>"],
  "requires_sql": <true if tabular_aggregation, else false>,
  "confidence": <0.0-1.0>
}}

For simple queries, sub_queries should contain only the original query.
For multi_hop or comparison, decompose into 2-3 focused sub-queries.

Query: {query}"""


# ---------------------------------------------------------------------------
# Agent 2 — Retrieval grader (CRAG-style)
# ---------------------------------------------------------------------------

RETRIEVAL_GRADER = """You are a retrieval quality judge.

Evaluate whether the retrieved chunk is relevant to answering the sub-query.

Respond with valid JSON only:
{{
  "grade": "<Correct|Incorrect|Ambiguous>",
  "confidence": <0.0-1.0>,
  "reason": "<one sentence>"
}}

Sub-query: {query}
Retrieved chunk: {chunk}"""


# ---------------------------------------------------------------------------
# Agent 3 — Reasoning / synthesis
# ---------------------------------------------------------------------------

REASONING_SYNTHESIS = """You are a precise analytical assistant. Answer the question using ONLY \
the provided context chunks. Every claim must be traceable to a specific source.

Output format — MUST be valid markdown with these exact sections, in this order:

## Answer
A 2-4 sentence direct answer with inline [Source N] citations on every factual claim.

## Key Points
- Bullet point with citation [Source N]
- Bullet point with citation [Source N]
- (3-6 bullets total — only include genuinely distinct, sourced points)

## Reasoning
Show your reasoning step-by-step. For numerical questions, include calculations.

## Sources Used
- [Source N] — short label of what this source contributed
- (one bullet per source you actually cited above)

Rules:
- Cite sources inline as [Source N] after each claim
- If context is insufficient, in the Answer section state exactly what information is missing and stop — do not invent facts
- Do not add sections beyond the four listed
- Do not include preamble before "## Answer"

Context chunks:
{context}

Question: {question}
"""

TEXT_TO_SQL = """You are a SQL expert. Generate a SQLite SELECT query to answer the question.

Available tables and columns:
{schema}

Rules:
- Output ONLY the SQL query — no explanation, no markdown
- Use only SELECT statements — never INSERT, UPDATE, DELETE, DROP
- Use exact column names from the schema
- If the question cannot be answered from the schema, output: SELECT 'insufficient_schema' AS error

Question: {question}

SQL:"""


# ---------------------------------------------------------------------------
# Agent 4 — Validation / hallucination detection
# ---------------------------------------------------------------------------

VALIDATION_FACT_CHECK = """You are a fact-checking agent. Verify whether each claim in the \
response is supported by the provided source chunks.

Respond with valid JSON only:
{{
  "passed": <true if all claims are supported, else false>,
  "unsupported_claims": ["<exact quote of unsupported claim>"],
  "feedback": "<one paragraph explaining what to fix if passed=false, else 'All claims verified.'>"
}}

Source chunks:
{context}

Response to verify:
{response}"""
