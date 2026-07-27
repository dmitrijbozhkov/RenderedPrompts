from __future__ import annotations

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import Column, Integer, MetaData, Table, Text


metadata = MetaData()

documents = Table(
    "documents",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("content", Text, nullable=False),
    Column("embedding", VECTOR(), nullable=False),
)
