from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


BASE_DIR = Path(__file__).resolve().parent


def load_env_file(path: Path = BASE_DIR / ".env") -> None:
    if not path.exists():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


load_env_file()

DB_PATH = Path(os.getenv("DB_PATH", BASE_DIR / "storage" / "app.db"))
if not DB_PATH.is_absolute():
    DB_PATH = BASE_DIR / DB_PATH


def ensure_storage_dir() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def get_conn() -> sqlite3.Connection:
    ensure_storage_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def get_enabled_channels() -> list[dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM channels
            WHERE enabled = 1
            ORDER BY priority DESC, id ASC
            """
        ).fetchall()
    return rows_to_dicts(rows)


def get_channel_by_source(source_id: str) -> dict[str, Any] | None:
    with connection() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM channels
            WHERE channel_id = ?
            LIMIT 1
            """,
            (source_id,),
        ).fetchone()
    return dict(row) if row else None


def get_channel_rules(channel_id: str) -> list[dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM clean_rules
            WHERE channel_id = ?
              AND enabled = 1
            ORDER BY priority DESC, id ASC
            """,
            (channel_id,),
        ).fetchall()
    return rows_to_dicts(rows)


def get_targets() -> dict[str, str]:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT type, target_channel_id
            FROM targets
            WHERE enabled = 1
            """
        ).fetchall()
    return {row["type"]: row["target_channel_id"] for row in rows}


def get_categories(enabled_only: bool = True) -> list[dict[str, Any]]:
    where_clause = "WHERE enabled = 1" if enabled_only else ""
    with connection() as conn:
        rows = conn.execute(
            f"""
            SELECT name, label, enabled, priority
            FROM categories
            {where_clause}
            ORDER BY priority DESC, name ASC
            """
        ).fetchall()
    return rows_to_dicts(rows)


def get_classify_rules() -> list[dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM classify_rules
            WHERE enabled = 1
            ORDER BY weight DESC, id ASC
            """
        ).fetchall()
    return rows_to_dicts(rows)


def get_setting(key: str, default: str | None = None) -> str | None:
    with connection() as conn:
        row = conn.execute(
            """
            SELECT value
            FROM settings
            WHERE key = ?
            """,
            (key,),
        ).fetchone()
    return row["value"] if row else default


def get_bool_setting(key: str, default: bool = False) -> bool:
    value = get_setting(key)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def get_float_setting(key: str, default: float) -> float:
    value = get_setting(key)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def get_int_setting(key: str, default: int) -> int:
    value = get_setting(key)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def save_forwarded_message(
    *,
    source_channel_id: str,
    source_message_id: int,
    target_channel_id: str,
    target_message_id: int | None,
    category: str,
    text_hash: str | None,
) -> None:
    with connection() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO forwarded_messages (
                source_channel_id,
                source_message_id,
                target_channel_id,
                target_message_id,
                category,
                text_hash
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                source_channel_id,
                source_message_id,
                target_channel_id,
                target_message_id,
                category,
                text_hash,
            ),
        )


def is_source_message_forwarded(source_channel_id: str, source_message_id: int) -> bool:
    with connection() as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM forwarded_messages
            WHERE source_channel_id = ?
              AND source_message_id = ?
            LIMIT 1
            """,
            (source_channel_id, source_message_id),
        ).fetchone()
    return bool(row)


def make_group_key(source_channel_id: str, grouped_id: int | str) -> str:
    return f"{source_channel_id}:{grouped_id}"


def is_source_group_forwarded(group_key: str) -> bool:
    with connection() as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM forwarded_groups
            WHERE group_key = ?
            LIMIT 1
            """,
            (group_key,),
        ).fetchone()
    return bool(row)


def save_forwarded_group(
    *,
    group_key: str,
    source_channel_id: str,
    grouped_id: int | str,
    first_source_message_id: int | None,
    target_channel_id: str,
    target_message_ids: list[int],
    category: str,
    text_hash: str | None,
) -> None:
    with connection() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO forwarded_groups (
                group_key,
                source_channel_id,
                grouped_id,
                first_source_message_id,
                target_channel_id,
                target_message_ids,
                category,
                text_hash
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                group_key,
                source_channel_id,
                str(grouped_id),
                first_source_message_id,
                target_channel_id,
                json.dumps(target_message_ids, ensure_ascii=False),
                category,
                text_hash,
            ),
        )
