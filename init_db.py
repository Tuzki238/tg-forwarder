from __future__ import annotations

from db import DB_PATH, connection, ensure_storage_dir


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS channels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id TEXT NOT NULL UNIQUE,
    channel_name TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    priority INTEGER NOT NULL DEFAULT 50,
    default_type TEXT NOT NULL DEFAULT 'auto',
    keep_media INTEGER NOT NULL DEFAULT 1,
    remove_urls INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS categories (
    name TEXT PRIMARY KEY,
    label TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    priority INTEGER NOT NULL DEFAULT 50,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS targets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL UNIQUE,
    target_channel_id TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS clean_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id TEXT NOT NULL,
    rule_type TEXT NOT NULL
        CHECK (rule_type IN ('cut_after', 'remove_keyword', 'regex', 'drop_if_keyword')),
    rule_value TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 50,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (channel_id) REFERENCES channels(channel_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS classify_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT NOT NULL,
    category TEXT NOT NULL,
    weight INTEGER NOT NULL DEFAULT 50,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    description TEXT,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dedup_hash (
    hash TEXT PRIMARY KEY,
    normalized_text TEXT NOT NULL,
    original_text TEXT,
    source_channel_id TEXT,
    source_message_id INTEGER,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS semantic_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text_hash TEXT NOT NULL UNIQUE,
    normalized_text TEXT NOT NULL,
    embedding BLOB,
    model_name TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS forwarded_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_channel_id TEXT NOT NULL,
    source_message_id INTEGER NOT NULL,
    target_channel_id TEXT NOT NULL,
    target_message_id INTEGER,
    category TEXT NOT NULL,
    text_hash TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (source_channel_id, source_message_id)
);

CREATE TABLE IF NOT EXISTS forwarded_groups (
    group_key TEXT PRIMARY KEY,
    source_channel_id TEXT NOT NULL,
    grouped_id TEXT NOT NULL,
    first_source_message_id INTEGER,
    target_channel_id TEXT NOT NULL,
    target_message_ids TEXT,
    category TEXT NOT NULL,
    text_hash TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS message_map (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_channel_id TEXT NOT NULL,
    source_message_id INTEGER NOT NULL,
    target_channel_id TEXT NOT NULL,
    target_message_id INTEGER NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_channels_enabled
    ON channels(enabled, priority);

CREATE INDEX IF NOT EXISTS idx_categories_enabled
    ON categories(enabled, priority);

CREATE INDEX IF NOT EXISTS idx_clean_rules_channel
    ON clean_rules(channel_id, enabled, priority);

CREATE INDEX IF NOT EXISTS idx_classify_rules_enabled
    ON classify_rules(enabled, weight);

CREATE INDEX IF NOT EXISTS idx_forwarded_messages_source
    ON forwarded_messages(source_channel_id, source_message_id);

CREATE INDEX IF NOT EXISTS idx_forwarded_groups_source
    ON forwarded_groups(source_channel_id, grouped_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_message_map_unique
    ON message_map(source_channel_id, source_message_id, target_channel_id);

CREATE INDEX IF NOT EXISTS idx_message_map_lookup
    ON message_map(source_channel_id, source_message_id);
"""


DEFAULT_SETTINGS = [
    ("hash_enabled", "true", "是否启用 Hash 完全去重"),
    ("semantic_enabled", "false", "是否启用语义去重扩展"),
    ("send_delay_seconds", "1", "每次转发后的等待秒数"),
    ("default_category", "news", "自动分类未命中时的默认分类"),
    ("poll_enabled", "true", "是否启用轮询补偿"),
    ("poll_interval_seconds", "20", "轮询补偿间隔秒数"),
    ("poll_batch_limit", "20", "每次轮询读取的最大消息数"),
    ("config_refresh_seconds", "10", "主程序刷新数据库配置的间隔秒数"),
    ("web_host", "127.0.0.1", "Web 管理后台监听地址"),
    ("web_port", "8080", "Web 管理后台监听端口"),
]


MIGRATIONS: dict[str, list[tuple[str, str]]] = {
    "channels": [
        ("created_at", "created_at DATETIME"),
        ("updated_at", "updated_at DATETIME"),
    ],
    "targets": [
        ("enabled", "enabled INTEGER NOT NULL DEFAULT 1"),
        ("created_at", "created_at DATETIME"),
        ("updated_at", "updated_at DATETIME"),
    ],
    "categories": [
        ("label", "label TEXT"),
        ("enabled", "enabled INTEGER NOT NULL DEFAULT 1"),
        ("priority", "priority INTEGER NOT NULL DEFAULT 50"),
        ("created_at", "created_at DATETIME"),
        ("updated_at", "updated_at DATETIME"),
    ],
    "clean_rules": [
        ("priority", "priority INTEGER NOT NULL DEFAULT 50"),
        ("created_at", "created_at DATETIME"),
    ],
    "classify_rules": [
        ("created_at", "created_at DATETIME"),
    ],
    "settings": [
        ("description", "description TEXT"),
        ("updated_at", "updated_at DATETIME"),
    ],
    "dedup_hash": [
        ("normalized_text", "normalized_text TEXT"),
        ("original_text", "original_text TEXT"),
        ("source_channel_id", "source_channel_id TEXT"),
        ("source_message_id", "source_message_id INTEGER"),
    ],
    "semantic_cache": [
        ("text_hash", "text_hash TEXT"),
        ("normalized_text", "normalized_text TEXT"),
        ("model_name", "model_name TEXT"),
    ],
}


def table_columns(conn, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row["name"] for row in rows}


def table_sql(conn, table_name: str) -> str:
    row = conn.execute(
        """
        SELECT sql
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?
        """,
        (table_name,),
    ).fetchone()
    return row["sql"] if row else ""


def rebuild_table_without_category_check(conn, table_name: str, create_sql: str, copy_sql: str) -> None:
    current_sql = table_sql(conn, table_name)
    if "CHECK" not in current_sql:
        return

    backup_table = f"{table_name}_old"
    conn.execute(f"DROP TABLE IF EXISTS {backup_table}")
    conn.execute(f"ALTER TABLE {table_name} RENAME TO {backup_table}")
    conn.execute(create_sql)
    conn.execute(copy_sql)
    conn.execute(f"DROP TABLE {backup_table}")


def remove_legacy_category_checks(conn) -> None:
    conn.execute("PRAGMA foreign_keys = OFF")
    rebuild_table_without_category_check(
        conn,
        "channels",
        """
        CREATE TABLE channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id TEXT NOT NULL UNIQUE,
            channel_name TEXT,
            enabled INTEGER NOT NULL DEFAULT 1,
            priority INTEGER NOT NULL DEFAULT 50,
            default_type TEXT NOT NULL DEFAULT 'auto',
            keep_media INTEGER NOT NULL DEFAULT 1,
            remove_urls INTEGER NOT NULL DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        INSERT INTO channels (
            id,
            channel_id,
            channel_name,
            enabled,
            priority,
            default_type,
            keep_media,
            remove_urls,
            created_at,
            updated_at
        )
        SELECT
            id,
            channel_id,
            channel_name,
            enabled,
            priority,
            default_type,
            keep_media,
            remove_urls,
            created_at,
            updated_at
        FROM channels_old
        """,
    )
    rebuild_table_without_category_check(
        conn,
        "targets",
        """
        CREATE TABLE targets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL UNIQUE,
            target_channel_id TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        INSERT INTO targets (
            id,
            type,
            target_channel_id,
            enabled,
            created_at,
            updated_at
        )
        SELECT
            id,
            type,
            target_channel_id,
            enabled,
            created_at,
            updated_at
        FROM targets_old
        """,
    )
    rebuild_table_without_category_check(
        conn,
        "classify_rules",
        """
        CREATE TABLE classify_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT NOT NULL,
            category TEXT NOT NULL,
            weight INTEGER NOT NULL DEFAULT 50,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        INSERT INTO classify_rules (
            id,
            keyword,
            category,
            weight,
            enabled,
            created_at
        )
        SELECT
            id,
            keyword,
            category,
            weight,
            enabled,
            created_at
        FROM classify_rules_old
        """,
    )
    rebuild_table_without_category_check(
        conn,
        "forwarded_messages",
        """
        CREATE TABLE forwarded_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_channel_id TEXT NOT NULL,
            source_message_id INTEGER NOT NULL,
            target_channel_id TEXT NOT NULL,
            target_message_id INTEGER,
            category TEXT NOT NULL,
            text_hash TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (source_channel_id, source_message_id)
        )
        """,
        """
        INSERT OR IGNORE INTO forwarded_messages (
            id,
            source_channel_id,
            source_message_id,
            target_channel_id,
            target_message_id,
            category,
            text_hash,
            created_at
        )
        SELECT
            id,
            source_channel_id,
            source_message_id,
            target_channel_id,
            target_message_id,
            category,
            text_hash,
            created_at
        FROM forwarded_messages_old
        """,
    )
    conn.execute("PRAGMA foreign_keys = ON")


def sync_categories(conn) -> None:
    defaults = [("news", "新闻"), ("post", "投稿")]
    conn.executemany(
        """
        INSERT INTO categories (name, label, enabled, priority)
        VALUES (?, ?, 1, 100)
        ON CONFLICT(name) DO UPDATE SET
            label = COALESCE(categories.label, excluded.label)
        """,
        defaults,
    )

    category_names = set()
    for row in conn.execute("SELECT type AS name FROM targets WHERE type <> ''"):
        category_names.add(row["name"])
    for row in conn.execute("SELECT category AS name FROM classify_rules WHERE category <> ''"):
        category_names.add(row["name"])
    for row in conn.execute("SELECT default_type AS name FROM channels WHERE default_type <> 'auto' AND default_type <> ''"):
        category_names.add(row["name"])
    for row in conn.execute("SELECT category AS name FROM forwarded_messages WHERE category <> ''"):
        category_names.add(row["name"])

    conn.executemany(
        """
        INSERT INTO categories (name, label, enabled, priority)
        VALUES (?, ?, 1, 50)
        ON CONFLICT(name) DO NOTHING
        """,
        [(name, name) for name in sorted(category_names)],
    )


def sync_default_settings(conn) -> None:
    conn.executemany(
        """
        INSERT INTO settings (key, value, description)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO NOTHING
        """,
        DEFAULT_SETTINGS,
    )


def sync_message_map(conn) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO message_map (
            source_channel_id,
            source_message_id,
            target_channel_id,
            target_message_id,
            created_at
        )
        SELECT
            source_channel_id,
            source_message_id,
            target_channel_id,
            target_message_id,
            created_at
        FROM forwarded_messages
        WHERE target_message_id IS NOT NULL
        """
    )


def migrate_existing_db(conn) -> None:
    for table_name, columns in MIGRATIONS.items():
        existing_columns = table_columns(conn, table_name)
        for column_name, column_sql in columns:
            if column_name not in existing_columns:
                conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_sql}")

    dedup_columns = table_columns(conn, "dedup_hash")
    if "text" in dedup_columns and "normalized_text" in dedup_columns:
        conn.execute(
            """
            UPDATE dedup_hash
            SET normalized_text = COALESCE(normalized_text, text),
                original_text = COALESCE(original_text, text)
            WHERE text IS NOT NULL
            """
        )

    remove_legacy_category_checks(conn)
    sync_categories(conn)
    sync_default_settings(conn)
    sync_message_map(conn)


def init_db() -> None:
    ensure_storage_dir()
    with connection() as conn:
        conn.executescript(SCHEMA_SQL)
        migrate_existing_db(conn)
        conn.executescript(INDEX_SQL)


if __name__ == "__main__":
    init_db()
    print(f"数据库初始化完成: {DB_PATH}")
