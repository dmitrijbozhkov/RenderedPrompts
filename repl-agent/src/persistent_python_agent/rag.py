from __future__ import annotations

from collections.abc import Sequence

from paradedb.sqlalchemy import pdb, search
from sqlalchemy import Float, Select, func, literal, select, union_all

from .models import documents


def build_hybrid_rrf_query(
    query: str,
    query_embedding: Sequence[float],
    *,
    limit: int,
    candidate_limit: int = 20,
    rrf_k: float = 60.0,
) -> Select:
    """Build a ParadeDB BM25 + pgvector cosine-distance RRF query."""
    terms = query.split()
    if not terms:
        raise ValueError("query must contain at least one search term")

    fulltext = (
        select(
            documents.c.id.label("id"),
            func.row_number()
            .over(order_by=pdb.score(documents.c.id).desc())
            .label("rank"),
        )
        .where(search.match_any(documents.c.content, *terms))
        .order_by(pdb.score(documents.c.id).desc())
        .limit(candidate_limit)
        .cte("fulltext")
    )

    semantic_distance = documents.c.embedding.cosine_distance(query_embedding)
    semantic = (
        select(
            documents.c.id.label("id"),
            func.row_number().over(order_by=semantic_distance).label("rank"),
        )
        .order_by(semantic_distance)
        .limit(candidate_limit)
        .cte("semantic")
    )

    rrf_fulltext = select(
        fulltext.c.id,
        (literal(1.0) / (literal(rrf_k) + fulltext.c.rank)).label("score"),
    )
    rrf_semantic = select(
        semantic.c.id,
        (literal(1.0) / (literal(rrf_k) + semantic.c.rank)).label("score"),
    )
    rrf = union_all(rrf_fulltext, rrf_semantic).cte("rrf")
    hybrid_score = func.sum(rrf.c.score)

    return (
        select(
            documents.c.id,
            documents.c.content,
            hybrid_score.cast(Float).label("hybrid_score"),
        )
        .join(rrf, rrf.c.id == documents.c.id)
        .group_by(documents.c.id, documents.c.content)
        .order_by(hybrid_score.desc())
        .limit(limit)
    )
