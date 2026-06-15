from __future__ import annotations

import asyncio
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from telethon import TelegramClient, events, utils

from classifier.classifier import classify_message
from cleaner.cleaner import clean_message_with_entities
from db import (
    get_bool_setting,
    get_categories,
    get_enabled_channels,
    get_float_setting,
    get_int_setting,
    get_setting,
    get_targets,
    is_source_group_forwarded,
    is_source_message_forwarded,
    make_group_key,
    save_forwarded_group,
    save_forwarded_message,
)
from dedup.hash_dedup import is_hash_duplicate, make_hash
from dedup.semantic_dedup import is_semantic_duplicate
from init_db import init_db
from sender.telegram_sender import send_media_group, send_message, sent_message_ids


BASE_DIR = Path(__file__).resolve().parent
LOCK_FILE = BASE_DIR / "storage" / "main.lock"
LOG_FILE = BASE_DIR / "storage" / "forwarder.log"


@dataclass(frozen=True)
class ForwarderConfig:
    channels: list[dict]
    channels_by_id: dict[str, dict]
    channel_entities: dict[str, object]
    targets: dict[str, str]
    target_chats: dict[str, object]
    fallback_category: str
    hash_enabled: bool
    send_delay_seconds: float
    poll_enabled: bool
    poll_interval_seconds: float
    poll_batch_limit: int
    config_refresh_seconds: float


@dataclass
class RuntimeConfig:
    client: TelegramClient
    snapshot: ForwarderConfig | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def refresh(self, *, require_ready: bool = False) -> ForwarderConfig:
        previous_entities = self.snapshot.channel_entities if self.snapshot else {}
        snapshot = await build_forwarder_config(
            self.client,
            previous_entities=previous_entities,
            require_ready=require_ready,
        )
        async with self.lock:
            self.snapshot = snapshot
        logging.info(
            "Config refreshed: sources=%s targets=%s refresh=%ss",
            len(snapshot.channels),
            snapshot.targets,
            snapshot.config_refresh_seconds,
        )
        return snapshot

    async def get(self) -> ForwarderConfig:
        async with self.lock:
            if self.snapshot is None:
                raise RuntimeError("Forwarder config has not been loaded")
            return self.snapshot


class SingleInstance:
    def __init__(self, lock_file: Path) -> None:
        self.lock_file = lock_file
        self.handle = None

    def __enter__(self) -> "SingleInstance":
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.lock_file.open("w", encoding="utf-8")

        if os.name == "nt":
            import msvcrt

            try:
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise RuntimeError("main.py 已经在运行，请先关闭旧窗口或结束旧的 Python 进程") from exc
        else:
            import fcntl

            try:
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise RuntimeError("main.py 已经在运行，请先关闭旧窗口或结束旧的 Python 进程") from exc

        self.handle.write(str(os.getpid()))
        self.handle.flush()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if not self.handle:
            return

        if os.name == "nt":
            import msvcrt

            self.handle.seek(0)
            msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)

        self.handle.close()


def load_env_file(path: Path = BASE_DIR / ".env") -> None:
    if not path.exists():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"缺少环境变量 {name}，请在 .env 中配置")
    return value


def parse_chat_ref(value: str):
    value = value.strip()
    if value.lstrip("-").isdigit():
        return int(value)
    return value


def setup_logging() -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def get_event_source_keys(event) -> list[str]:
    keys = []
    if event.chat_id is not None:
        keys.append(str(event.chat_id))

    username = getattr(event.chat, "username", None)
    if username:
        keys.append(f"@{username}")
        keys.append(username)

    return keys


async def build_channel_runtime(
    client: TelegramClient,
    channels: list[dict],
    previous_entities: dict[str, object] | None = None,
) -> tuple[dict[str, dict], dict[str, object]]:
    previous_entities = previous_entities or {}
    channels_by_id = {channel["channel_id"]: channel for channel in channels}
    entities = {}

    for channel in channels:
        source_channel_id = channel["channel_id"]
        entity = previous_entities.get(source_channel_id)
        try:
            if entity is None:
                entity = await client.get_entity(parse_chat_ref(source_channel_id))
        except Exception:
            logging.exception("Failed to resolve source channel %s", source_channel_id)
            continue

        entities[source_channel_id] = entity
        peer_id = utils.get_peer_id(entity)
        channels_by_id[str(peer_id)] = channel

        username = getattr(entity, "username", None)
        if username:
            channels_by_id[username] = channel
            channels_by_id[f"@{username}"] = channel

    return channels_by_id, entities


async def build_forwarder_config(
    client: TelegramClient,
    *,
    previous_entities: dict[str, object] | None = None,
    require_ready: bool = False,
) -> ForwarderConfig:
    channels = get_enabled_channels()
    if require_ready and not channels:
        raise RuntimeError("SQLite 中没有启用的来源频道，请先在 Web 后台写入 channels 配置")

    targets = get_targets()
    if require_ready and not targets:
        raise RuntimeError("SQLite 中没有启用的目标频道，请先在 Web 后台配置至少一个目标频道")

    categories = {category["name"] for category in get_categories()}
    if require_ready and not categories:
        raise RuntimeError("SQLite 中没有启用的信息分类，请先在 Web 后台配置至少一个分类")

    channels_by_id, channel_entities = await build_channel_runtime(
        client,
        channels,
        previous_entities=previous_entities,
    )
    target_chats = {
        category: parse_chat_ref(target_channel_id)
        for category, target_channel_id in targets.items()
    }

    fallback_category = get_setting("default_category", "news") or "news"
    if targets and fallback_category not in targets:
        fallback_category = next(iter(targets))

    return ForwarderConfig(
        channels=channels,
        channels_by_id=channels_by_id,
        channel_entities=channel_entities,
        targets=targets,
        target_chats=target_chats,
        fallback_category=fallback_category,
        hash_enabled=get_bool_setting("hash_enabled", True),
        send_delay_seconds=get_float_setting("send_delay_seconds", 1.0),
        poll_enabled=get_bool_setting("poll_enabled", True),
        poll_interval_seconds=max(get_float_setting("poll_interval_seconds", 20.0), 1.0),
        poll_batch_limit=max(get_int_setting("poll_batch_limit", 20), 1),
        config_refresh_seconds=max(get_float_setting("config_refresh_seconds", 10.0), 1.0),
    )


async def refresh_config_loop(runtime_config: RuntimeConfig) -> None:
    while True:
        snapshot = await runtime_config.get()
        await asyncio.sleep(snapshot.config_refresh_seconds)
        try:
            await runtime_config.refresh()
        except Exception:
            logging.exception("Config refresh failed; keeping previous config")


async def process_source_message(
    client: TelegramClient,
    *,
    message,
    source_channel: dict,
    targets: dict[str, str],
    target_chats: dict[str, object],
    fallback_category: str,
    hash_enabled: bool,
    send_delay_seconds: float,
) -> bool:
    source_channel_id = source_channel["channel_id"]
    source_message_id = message.id

    if getattr(message, "grouped_id", None):
        logging.info(
            "Skipped album child in single-message path: source=%s msg_id=%s grouped_id=%s",
            source_channel_id,
            source_message_id,
            message.grouped_id,
        )
        return False

    if is_source_message_forwarded(source_channel_id, source_message_id):
        logging.info("Skipped already forwarded: source=%s msg_id=%s", source_channel_id, source_message_id)
        return False

    logging.info("New message: source=%s msg_id=%s", source_channel_id, source_message_id)
    raw_text = message.raw_text or ""
    cleaned_text, formatting_entities = clean_message_with_entities(
        raw_text,
        message.entities,
        source_channel_id,
        remove_urls=bool(source_channel["remove_urls"]),
    )
    if cleaned_text is None:
        logging.info("Skipped by clean drop rule: source=%s msg_id=%s", source_channel_id, source_message_id)
        return False

    has_media = bool(message.media)
    if not cleaned_text and not has_media:
        logging.info("Skipped empty message: source=%s msg_id=%s", source_channel_id, source_message_id)
        return False

    if cleaned_text and hash_enabled:
        duplicate = is_hash_duplicate(
            cleaned_text,
            source_channel_id=source_channel_id,
            source_message_id=source_message_id,
        )
        if duplicate:
            logging.info("Skipped duplicate hash: source=%s msg_id=%s", source_channel_id, source_message_id)
            return False

    if cleaned_text and is_semantic_duplicate(cleaned_text):
        logging.info("Skipped semantic duplicate: source=%s msg_id=%s", source_channel_id, source_message_id)
        return False

    category = classify_message(cleaned_text or "", source_channel["default_type"])
    if category not in targets:
        fallback = fallback_category if fallback_category in targets else next(iter(targets), None)
        if fallback is None:
            logging.error(
                "No enabled target channel, skipped: source=%s msg_id=%s category=%s",
                source_channel_id,
                source_message_id,
                category,
            )
            return False
        logging.warning(
            "Category has no target, falling back: category=%s fallback=%s",
            category,
            fallback,
        )
        category = fallback

    target_channel_id = targets[category]
    target_chat = target_chats.get(category)
    if target_chat is None:
        logging.error(
            "Target chat is not configured, skipped: source=%s msg_id=%s category=%s",
            source_channel_id,
            source_message_id,
            category,
        )
        return False
    logging.info(
        "Forwarding: source=%s msg_id=%s category=%s target=%s",
        source_channel_id,
        source_message_id,
        category,
        target_channel_id,
    )
    sent_message = await send_message(
        client,
        target_channel_id=target_chat,
        text=cleaned_text or "",
        formatting_entities=formatting_entities if cleaned_text else None,
        media=message.media,
        keep_media=bool(source_channel["keep_media"]),
    )

    sent_message_id = getattr(sent_message, "id", None)
    save_forwarded_message(
        source_channel_id=source_channel_id,
        source_message_id=source_message_id,
        target_channel_id=target_channel_id,
        target_message_id=sent_message_id,
        category=category,
        text_hash=make_hash(cleaned_text) if cleaned_text else None,
    )
    logging.info("Forwarded: target_msg_id=%s", sent_message_id)

    if send_delay_seconds > 0:
        await asyncio.sleep(send_delay_seconds)
    return True


def choose_album_caption_message(messages: list) -> object | None:
    for message in sorted(messages, key=lambda item: item.id):
        if (message.raw_text or "").strip():
            return message
    return None


async def process_source_album(
    client: TelegramClient,
    *,
    messages: list,
    source_channel: dict,
    targets: dict[str, str],
    target_chats: dict[str, object],
    fallback_category: str,
    hash_enabled: bool,
    send_delay_seconds: float,
) -> bool:
    album_messages = sorted(messages, key=lambda item: item.id)
    if not album_messages:
        return False

    grouped_id = getattr(album_messages[0], "grouped_id", None)
    if not grouped_id:
        return False

    source_channel_id = source_channel["channel_id"]
    group_key = make_group_key(source_channel_id, grouped_id)
    if is_source_group_forwarded(group_key):
        logging.info("Skipped already forwarded album: group_key=%s", group_key)
        return False

    caption_message = choose_album_caption_message(album_messages)
    raw_text = caption_message.raw_text if caption_message else ""
    raw_entities = caption_message.entities if caption_message else None
    cleaned_text, formatting_entities = clean_message_with_entities(
        raw_text or "",
        raw_entities,
        source_channel_id,
        remove_urls=bool(source_channel["remove_urls"]),
    )
    if cleaned_text is None:
        logging.info("Skipped album by clean drop rule: group_key=%s", group_key)
        return False

    if not cleaned_text and source_channel["default_type"] == "auto":
        logging.info("Skipped captionless auto album: group_key=%s", group_key)
        return False

    if cleaned_text and hash_enabled:
        duplicate = is_hash_duplicate(
            cleaned_text,
            source_channel_id=source_channel_id,
            source_message_id=album_messages[0].id,
        )
        if duplicate:
            logging.info("Skipped duplicate album hash: group_key=%s", group_key)
            return False

    if cleaned_text and is_semantic_duplicate(cleaned_text):
        logging.info("Skipped semantic duplicate album: group_key=%s", group_key)
        return False

    category = classify_message(cleaned_text or "", source_channel["default_type"])
    if category not in targets:
        fallback = fallback_category if fallback_category in targets else next(iter(targets), None)
        if fallback is None:
            logging.error(
                "No enabled target channel, skipped album: group_key=%s category=%s",
                group_key,
                category,
            )
            return False
        logging.warning(
            "Album category has no target, falling back: category=%s fallback=%s group_key=%s",
            category,
            fallback,
            group_key,
        )
        category = fallback

    target_channel_id = targets[category]
    target_chat = target_chats.get(category)
    if target_chat is None:
        logging.error(
            "Target chat is not configured, skipped album: group_key=%s category=%s",
            group_key,
            category,
        )
        return False
    media_items = [message.media for message in album_messages if message.media]
    logging.info(
        "Forwarding album: group_key=%s messages=%s category=%s target=%s",
        group_key,
        [message.id for message in album_messages],
        category,
        target_channel_id,
    )
    sent = await send_media_group(
        client,
        target_channel_id=target_chat,
        text=cleaned_text or "",
        formatting_entities=formatting_entities if cleaned_text else None,
        media_items=media_items,
        keep_media=bool(source_channel["keep_media"]),
    )
    target_ids = sent_message_ids(sent)

    save_forwarded_group(
        group_key=group_key,
        source_channel_id=source_channel_id,
        grouped_id=grouped_id,
        first_source_message_id=album_messages[0].id,
        target_channel_id=target_channel_id,
        target_message_ids=target_ids,
        category=category,
        text_hash=make_hash(cleaned_text) if cleaned_text else None,
    )

    for index, source_message in enumerate(album_messages):
        target_message_id = target_ids[index] if index < len(target_ids) else (target_ids[0] if target_ids else None)
        save_forwarded_message(
            source_channel_id=source_channel_id,
            source_message_id=source_message.id,
            target_channel_id=target_channel_id,
            target_message_id=target_message_id,
            category=category,
            text_hash=make_hash(cleaned_text) if cleaned_text else None,
        )

    logging.info("Forwarded album: group_key=%s target_msg_ids=%s", group_key, target_ids)
    if send_delay_seconds > 0:
        await asyncio.sleep(send_delay_seconds)
    return True


async def init_poll_offsets(
    client: TelegramClient,
    channels: list[dict],
    channel_entities: dict[str, object],
) -> dict[str, int]:
    offsets = {}
    for channel in channels:
        source_channel_id = channel["channel_id"]
        entity = channel_entities.get(source_channel_id)
        if entity is None:
            offsets[source_channel_id] = 0
            continue
        try:
            messages = await client.get_messages(entity, limit=1)
            offsets[source_channel_id] = messages[0].id if messages else 0
            logging.info("Poll offset initialized: source=%s last_seen=%s", source_channel_id, offsets[source_channel_id])
        except Exception:
            logging.exception("Failed to initialize poll offset: source=%s", source_channel_id)
            offsets[source_channel_id] = 0
    return offsets


async def poll_new_messages(
    client: TelegramClient,
    *,
    runtime_config: RuntimeConfig,
) -> None:
    offsets: dict[str, int] = {}

    while True:
        snapshot = await runtime_config.get()
        try:
            if not snapshot.poll_enabled:
                await asyncio.sleep(snapshot.config_refresh_seconds)
                continue

            enabled_channel_ids = {channel["channel_id"] for channel in snapshot.channels}
            for old_channel_id in list(offsets):
                if old_channel_id not in enabled_channel_ids:
                    offsets.pop(old_channel_id, None)

            for channel in snapshot.channels:
                source_channel_id = channel["channel_id"]
                entity = snapshot.channel_entities.get(source_channel_id)
                if entity is None:
                    continue

                if source_channel_id not in offsets:
                    try:
                        latest = await client.get_messages(entity, limit=1)
                        offsets[source_channel_id] = latest[0].id if latest else 0
                        logging.info(
                            "Poll offset initialized: source=%s last_seen=%s",
                            source_channel_id,
                            offsets[source_channel_id],
                        )
                    except Exception:
                        logging.exception("Failed to initialize poll offset: source=%s", source_channel_id)
                        offsets[source_channel_id] = 0
                    continue

                last_seen = offsets.get(source_channel_id, 0)
                messages = await client.get_messages(entity, limit=snapshot.poll_batch_limit)
                new_messages = sorted(
                    [message for message in messages if message.id > last_seen],
                    key=lambda item: item.id,
                )

                grouped_messages = {}
                single_messages = []
                for message in new_messages:
                    grouped_id = getattr(message, "grouped_id", None)
                    if grouped_id:
                        grouped_messages.setdefault(str(grouped_id), []).append(message)
                    else:
                        single_messages.append(message)

                for album_messages in grouped_messages.values():
                    await process_source_album(
                        client,
                        messages=album_messages,
                        source_channel=channel,
                        targets=snapshot.targets,
                        target_chats=snapshot.target_chats,
                        fallback_category=snapshot.fallback_category,
                        hash_enabled=snapshot.hash_enabled,
                        send_delay_seconds=snapshot.send_delay_seconds,
                    )

                for message in single_messages:
                    await process_source_message(
                        client,
                        message=message,
                        source_channel=channel,
                        targets=snapshot.targets,
                        target_chats=snapshot.target_chats,
                        fallback_category=snapshot.fallback_category,
                        hash_enabled=snapshot.hash_enabled,
                        send_delay_seconds=snapshot.send_delay_seconds,
                    )

                if messages:
                    offsets[source_channel_id] = max(offsets.get(source_channel_id, 0), messages[0].id)
        except Exception:
            logging.exception("Polling fallback failed")

        await asyncio.sleep(snapshot.poll_interval_seconds)


async def main(*, initialize: bool = True) -> None:
    if initialize:
        setup_logging()
        logging.info("Initializing database")
        init_db()
        load_env_file()
    else:
        load_env_file()

    api_id = int(require_env("API_ID"))
    api_hash = require_env("API_HASH")
    session_name = os.getenv("SESSION_NAME", "tg_forwarder")

    client = TelegramClient(session_name, api_id, api_hash)
    runtime_config = RuntimeConfig(client)
    background_tasks: list[asyncio.Task] = []

    @client.on(events.Album())
    async def album_handler(event) -> None:
        try:
            snapshot = await runtime_config.get()
            source_keys = get_event_source_keys(event)
            source_channel = next(
                (snapshot.channels_by_id[key] for key in source_keys if key in snapshot.channels_by_id),
                None,
            )
            if not source_channel:
                return

            await process_source_album(
                client,
                messages=list(event.messages),
                source_channel=source_channel,
                targets=snapshot.targets,
                target_chats=snapshot.target_chats,
                fallback_category=snapshot.fallback_category,
                hash_enabled=snapshot.hash_enabled,
                send_delay_seconds=snapshot.send_delay_seconds,
            )
        except Exception:
            logging.exception("Album handler failed")

    @client.on(events.NewMessage())
    async def handler(event) -> None:
        try:
            snapshot = await runtime_config.get()
            source_keys = get_event_source_keys(event)
            source_channel = next(
                (snapshot.channels_by_id[key] for key in source_keys if key in snapshot.channels_by_id),
                None,
            )
            if not source_channel:
                return

            if getattr(event.message, "grouped_id", None):
                logging.info(
                    "Skipped album child while waiting for album handler: source=%s msg_id=%s grouped_id=%s",
                    source_channel["channel_id"],
                    event.message.id,
                    event.message.grouped_id,
                )
                return

            await process_source_message(
                client,
                message=event.message,
                source_channel=source_channel,
                targets=snapshot.targets,
                target_chats=snapshot.target_chats,
                fallback_category=snapshot.fallback_category,
                hash_enabled=snapshot.hash_enabled,
                send_delay_seconds=snapshot.send_delay_seconds,
            )
        except Exception:
            logging.exception("Handler failed")

    logging.info("Connecting Telegram")
    try:
        await client.start()
        initial_config = await runtime_config.refresh(require_ready=True)
        logging.info(
            "Loaded %s source channels: %s",
            len(initial_config.channels),
            [channel["channel_id"] for channel in initial_config.channels],
        )
        logging.info("Loaded targets: %s", initial_config.targets)

        background_tasks.append(asyncio.create_task(refresh_config_loop(runtime_config)))
        background_tasks.append(
            asyncio.create_task(
                poll_new_messages(
                    client,
                    runtime_config=runtime_config,
                )
            )
        )
        logging.info("Telegram forwarder started, listening %s source channels", len(initial_config.channels))
        await client.run_until_disconnected()
    finally:
        for task in background_tasks:
            task.cancel()
        if background_tasks:
            await asyncio.gather(*background_tasks, return_exceptions=True)
        if client.is_connected():
            await client.disconnect()
        logging.info("Telegram forwarder stopped")


if __name__ == "__main__":
    try:
        with SingleInstance(LOCK_FILE):
            asyncio.run(main())
    except KeyboardInterrupt:
        print("已停止 Telegram 转发程序")
    except RuntimeError as exc:
        print(f"启动失败: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
