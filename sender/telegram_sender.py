from __future__ import annotations

from telethon import TelegramClient


async def send_message(
    client: TelegramClient,
    *,
    target_channel_id,
    text: str,
    formatting_entities=None,
    media,
    keep_media: bool,
):
    if media and keep_media:
        return await client.send_file(
            target_channel_id,
            media,
            caption=text or None,
            formatting_entities=formatting_entities if text else None,
        )

    if text:
        return await client.send_message(
            target_channel_id,
            text,
            formatting_entities=formatting_entities,
        )

    return None


async def send_media_group(
    client: TelegramClient,
    *,
    target_channel_id,
    text: str,
    formatting_entities=None,
    media_items: list,
    keep_media: bool,
):
    if media_items and keep_media:
        return await client.send_file(
            target_channel_id,
            media_items,
            caption=text or None,
            formatting_entities=formatting_entities if text else None,
        )

    if text:
        return await client.send_message(
            target_channel_id,
            text,
            formatting_entities=formatting_entities,
        )

    return None


def sent_message_ids(sent_message) -> list[int]:
    if sent_message is None:
        return []
    if isinstance(sent_message, list):
        return [item.id for item in sent_message if getattr(item, "id", None) is not None]
    message_id = getattr(sent_message, "id", None)
    return [message_id] if message_id is not None else []
