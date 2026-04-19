"""Output layer: turn runtime results into the public query_result
envelope and human-readable explanations.

Output is a passive assembler. It MUST NOT call back into the runtime
for additional reasoning. If the explainer needs path data, the runtime
has already populated it in the QueryResult.
"""
