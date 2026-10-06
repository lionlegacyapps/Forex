"""Safe DATABASE_URL normalization for SQLAlchemy + Supabase PostgreSQL.

Never log or return the raw URL from this module.
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


def normalize_database_url(url: str) -> str:
    """Return a SQLAlchemy URL suitable for psycopg3 against Supabase/Postgres.

    - Maps ``postgres://`` / ``postgresql://`` → ``postgresql+psycopg://``
    - Leaves an existing ``postgresql+psycopg://`` scheme unchanged
    - Ensures ``sslmode=require`` for non-local hosts (Supabase requires TLS)
    """
    cleaned = url.strip()
    if not cleaned:
        raise ValueError("DATABASE_URL is empty")

    if cleaned.startswith("postgres://"):
        cleaned = "postgresql+psycopg://" + cleaned.removeprefix("postgres://")
    elif cleaned.startswith("postgresql://"):
        cleaned = "postgresql+psycopg://" + cleaned.removeprefix("postgresql://")
    elif not cleaned.startswith("postgresql+psycopg://"):
        # Allow other explicit SQLAlchemy dialects; do not rewrite unknown schemes.
        return cleaned

    parsed = urlparse(cleaned)
    host = (parsed.hostname or "").lower()
    is_local = host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".local")

    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if not is_local and "sslmode" not in {k.lower() for k in query}:
        query["sslmode"] = "require"

    # Preserve original query key casing for existing params; only add sslmode when needed.
    normalized_query = urlencode(query)
    return urlunparse(parsed._replace(query=normalized_query))
