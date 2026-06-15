from __future__ import annotations

import hashlib
import re

from db import connection


def normalize_for_hash(text: str) -> str:
    normalized = (text or "").strip().lower()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def make_hash(text: str) -> str:
    return hashlib.sha256(normalize_for_hash(text).encode("utf-8")).hexdigest()


def is_hash_duplicate(
    text: str,
    *,
    source_channel_id: str | None = None,
    source_message_id: int | None = None,
) -> bool:
    normalized_text = normalize_for_hash(text)
    if not normalized_text:
        return False

    text_hash = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
    with connection() as conn:
        row = conn.execute(
            """
            SELECT hash
            FROM dedup_hash
            WHERE hash = ?
            """,
            (text_hash,),
        ).fetchone()
        if row:
            return True

        conn.execute(
            """
            INSERT INTO dedup_hash (
                hash,
                normalized_text,
                original_text,
                source_channel_id,
                source_message_id
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                text_hash,
                normalized_text,
                text,
                source_channel_id,
                source_message_id,
            ),
        )
    return False
