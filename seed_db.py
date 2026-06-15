from __future__ import annotations

from init_db import init_db
from db import connection


TARGETS = [
    ("news", "-1003353956518", 1),
    ("post", "-1002949976380", 1),
]

CATEGORIES = [
    ("news", "新闻", 1, 100),
    ("post", "投稿", 1, 90),
]

CHANNELS = [
    (
        "-1003917067374",
        "测试频道",
        1,
        100,
        "news",
        1,
        1,
    ),
    (
        "-1002414842159",
        "缅甸安危头条/新闻头条",
        1,
        80,
        "auto",
        1,
        1,
    ),
]

CLEAN_RULES = [
    ("-1003917067374", "cut_after", "欢迎爆料：", 100, 1),
    ("-1003917067374", "remove_keyword", "广告合作", 90, 1),
    ("-1003917067374", "remove_keyword", "商务合作", 90, 1),
    ("-1002414842159", "cut_after", "✍️曝光-澄清投稿：", 120, 1),
    ("-1002414842159", "cut_after", "✍️商务-广告合作：", 110, 1),
    ("-1002414842159", "cut_after", "🎰", 100, 1),
    ("-1002414842159", "cut_after", "😀缅甸生活群", 100, 1),
    ("-1002414842159", "cut_after", "────────────", 90, 1),
    ("-1002414842159", "remove_keyword", "VIP群", 80, 1),
    ("-1002414842159", "regex", r"https?://\S+", 70, 1),
    ("-1002414842159", "regex", r"t\.me/\S+", 70, 1),
    ("-1002414842159", "regex", r"@\w+", 60, 1),
]

CLASSIFY_RULES = [
    ("投稿", "post", 100, 1),
    ("爆料", "post", 90, 1),
    ("网友反馈", "post", 80, 1),
    ("警方", "news", 95, 1),
    ("报案", "news", 95, 1),
    ("立案", "news", 95, 1),
    ("案发", "news", 90, 1),
    ("被盗", "news", 90, 1),
    ("查获", "news", 85, 1),
    ("快讯", "news", 80, 1),
    ("公告", "news", 80, 1),
    ("新闻", "news", 70, 1),
    ("仰光", "news", 65, 1),
]

SETTINGS = [
    ("hash_enabled", "true", "是否启用 Hash 完全去重"),
    ("semantic_enabled", "false", "是否启用语义去重占位逻辑"),
    ("similarity_threshold", "0.88", "语义去重相似度阈值"),
    ("semantic_model", "paraphrase-multilingual-MiniLM-L12-v2", "预留的 Embedding 模型名"),
    ("max_compare_messages", "3000", "语义去重最多比较的历史消息数"),
    ("send_delay_seconds", "1", "每次转发后的等待秒数"),
    ("default_category", "news", "自动分类未命中时的默认类型"),
]


def seed_db() -> None:
    init_db()
    with connection() as conn:
        conn.executemany(
            """
            INSERT INTO categories (name, label, enabled, priority)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                label = excluded.label,
                enabled = excluded.enabled,
                priority = excluded.priority,
                updated_at = CURRENT_TIMESTAMP
            """,
            CATEGORIES,
        )

        conn.executemany(
            """
            INSERT INTO targets (type, target_channel_id, enabled)
            VALUES (?, ?, ?)
            ON CONFLICT(type) DO UPDATE SET
                target_channel_id = excluded.target_channel_id,
                enabled = excluded.enabled,
                updated_at = CURRENT_TIMESTAMP
            """,
            TARGETS,
        )

        conn.executemany(
            """
            INSERT INTO channels (
                channel_id,
                channel_name,
                enabled,
                priority,
                default_type,
                keep_media,
                remove_urls
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(channel_id) DO UPDATE SET
                channel_name = excluded.channel_name,
                enabled = excluded.enabled,
                priority = excluded.priority,
                default_type = excluded.default_type,
                keep_media = excluded.keep_media,
                remove_urls = excluded.remove_urls,
                updated_at = CURRENT_TIMESTAMP
            """,
            CHANNELS,
        )

        source_ids = [channel[0] for channel in CHANNELS]
        conn.executemany(
            "DELETE FROM clean_rules WHERE channel_id = ?",
            [(source_id,) for source_id in source_ids],
        )
        conn.executemany(
            """
            INSERT INTO clean_rules (channel_id, rule_type, rule_value, priority, enabled)
            VALUES (?, ?, ?, ?, ?)
            """,
            CLEAN_RULES,
        )

        conn.execute("DELETE FROM classify_rules")
        conn.executemany(
            """
            INSERT INTO classify_rules (keyword, category, weight, enabled)
            VALUES (?, ?, ?, ?)
            """,
            CLASSIFY_RULES,
        )

        conn.executemany(
            """
            INSERT INTO settings (key, value, description)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                description = excluded.description,
                updated_at = CURRENT_TIMESTAMP
            """,
            SETTINGS,
        )


if __name__ == "__main__":
    seed_db()
    print("初始配置写入完成")
