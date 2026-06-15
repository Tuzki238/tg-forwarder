from __future__ import annotations

import copy
import re

from telethon.helpers import add_surrogate, del_surrogate

from db import get_channel_rules


URL_RE = re.compile(r"https?://\S+|t\.me/\S+|@\w+")


def clone_entity(entity, offset: int, length: int):
    cloned = copy.copy(entity)
    cloned.offset = offset
    cloned.length = length
    return cloned


def delete_range(text: str, entities: list, start: int, end: int) -> tuple[str, list]:
    if start >= end:
        return text, entities

    start = max(start, 0)
    end = min(end, len(text))
    deleted_len = end - start
    new_entities = []

    for entity in entities:
        entity_start = entity.offset
        entity_end = entity.offset + entity.length

        if entity_end <= start:
            new_entities.append(entity)
            continue

        if entity_start >= end:
            new_entities.append(clone_entity(entity, entity_start - deleted_len, entity.length))
            continue

        before_len = max(0, start - entity_start)
        after_len = max(0, entity_end - end)
        new_length = before_len + after_len
        if new_length <= 0:
            continue

        new_offset = entity_start if entity_start < start else start
        new_entities.append(clone_entity(entity, new_offset, new_length))

    return text[:start] + text[end:], new_entities


def delete_ranges(text: str, entities: list, ranges: list[tuple[int, int]]) -> tuple[str, list]:
    for start, end in sorted(ranges, reverse=True):
        text, entities = delete_range(text, entities, start, end)
    return text, entities


def find_literal_ranges(text: str, value: str) -> list[tuple[int, int]]:
    ranges = []
    start = 0
    while True:
        index = text.find(value, start)
        if index == -1:
            break
        ranges.append((index, index + len(value)))
        start = index + len(value)
    return ranges


def delete_regex_matches(text: str, entities: list, pattern: str) -> tuple[str, list]:
    try:
        ranges = [(match.start(), match.end()) for match in re.finditer(pattern, text)]
    except re.error:
        return text, entities
    return delete_ranges(text, entities, ranges)


def normalize_text_entities(text: str, entities: list) -> tuple[str, list]:
    ranges = [(match.start(), match.end() - 1) for match in re.finditer(r"[ \t]+\n", text)]
    text, entities = delete_ranges(text, entities, ranges)

    ranges = [(match.start() + 2, match.end()) for match in re.finditer(r"\n{3,}", text)]
    text, entities = delete_ranges(text, entities, ranges)

    leading = len(text) - len(text.lstrip())
    trailing_start = len(text.rstrip())
    ranges = []
    if trailing_start < len(text):
        ranges.append((trailing_start, len(text)))
    if leading > 0:
        ranges.append((0, leading))
    text, entities = delete_ranges(text, entities, ranges)

    valid_entities = [
        entity
        for entity in entities
        if entity.length > 0 and 0 <= entity.offset < len(text) and entity.offset + entity.length <= len(text)
    ]
    return text, valid_entities


def clean_message_with_entities(
    text: str,
    entities: list | None,
    channel_id: str,
    *,
    remove_urls: bool = False,
) -> tuple[str | None, list]:
    cleaned = add_surrogate(text or "")
    cleaned_entities = [copy.copy(entity) for entity in (entities or [])]

    for rule in get_channel_rules(channel_id):
        rule_type = rule["rule_type"]
        value = rule["rule_value"]

        if not value:
            continue

        value = add_surrogate(value)

        if rule_type == "drop_if_keyword" and value in cleaned:
            return None, []

        if rule_type == "cut_after" and value in cleaned:
            index = cleaned.find(value)
            cleaned, cleaned_entities = delete_range(cleaned, cleaned_entities, index, len(cleaned))
            continue

        if rule_type == "remove_keyword":
            cleaned, cleaned_entities = delete_ranges(cleaned, cleaned_entities, find_literal_ranges(cleaned, value))
            continue

        if rule_type == "regex":
            cleaned, cleaned_entities = delete_regex_matches(cleaned, cleaned_entities, value)

    if remove_urls:
        cleaned, cleaned_entities = delete_regex_matches(cleaned, cleaned_entities, URL_RE.pattern)

    cleaned, cleaned_entities = normalize_text_entities(cleaned, cleaned_entities)
    return del_surrogate(cleaned), cleaned_entities


def clean_message(
    text: str,
    channel_id: str,
    *,
    remove_urls: bool = False,
) -> str | None:
    cleaned, _ = clean_message_with_entities(text, None, channel_id, remove_urls=remove_urls)
    return cleaned
