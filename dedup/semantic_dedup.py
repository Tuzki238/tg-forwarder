from __future__ import annotations

from db import get_bool_setting


def is_semantic_duplicate(text: str) -> bool:
    """Extension point for future Embedding-based duplicate detection."""
    if not text.strip():
        return False

    if not get_bool_setting("semantic_enabled", False):
        return False

    # Keep this module dependency-free for now. A future implementation can:
    # 1. load settings.semantic_model;
    # 2. generate an embedding for the cleaned text;
    # 3. compare it with semantic_cache by settings.similarity_threshold;
    # 4. insert the new embedding when no duplicate is found.
    return False
