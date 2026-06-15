from __future__ import annotations

from db import get_categories, get_classify_rules, get_setting


def classify_message(text: str, default_type: str = "auto") -> str:
    valid_categories = {category["name"] for category in get_categories()}
    if default_type in valid_categories:
        return default_type

    normalized_text = (text or "").lower()
    for rule in get_classify_rules():
        keyword = rule["keyword"]
        category = rule["category"]
        if category in valid_categories and keyword.lower() in normalized_text:
            return category

    default_category = get_setting("default_category", "news")
    if default_category in valid_categories:
        return default_category
    if "news" in valid_categories:
        return "news"
    return next(iter(valid_categories), "news")
