#!/usr/bin/env python3
"""
Telegram Group Downloader
Baixa vídeos e arquivos de grupos do Telegram via API (MTProto).
"""

import os
import sys
import asyncio
import json
from pathlib import Path

from telethon import TelegramClient
from telethon.tl.types import (
    Channel,
    Chat,
    DocumentAttributeFilename,
    DocumentAttributeVideo,
    MessageMediaDocument,
    MessageMediaPhoto,
)

SESSION_NAME = "telegram_session"
CONFIG_FILE = Path(__file__).parent / "config.json"

MEDIA_FILTERS = {
    "1": {"label": "Apenas vídeos", "types": ["video"]},
    "2": {"label": "Apenas fotos", "types": ["photo"]},
    "3": {"label": "Apenas documentos/arquivos", "types": ["document"]},
    "4": {"label": "Tudo (vídeos + fotos + documentos)", "types": ["video", "photo", "document"]},
}


def load_credentials() -> tuple[str, str]:
    if CONFIG_FILE.exists():
        data = json.loads(CONFIG_FILE.read_text())
        api_id = data.get("api_id")
        api_hash = data.get("api_hash")
        if api_id and api_hash:
            return str(api_id), api_hash

    print(f"{'='*55}")
    print("  CONFIGURAÇÃO INICIAL")
    print(f"{'='*55}")
    print()
    print("  Para usar este script, você precisa de credenciais")
    print("  da API do Telegram. Siga os passos:")
    print()
    print("  1. Acesse: https://my.telegram.org")
    print("  2. Faça login com seu número de telefone")
    print("  3. Clique em 'API development tools'")
    print("  4. Crie um aplicativo (qualquer nome serve)")
    print("  5. Copie o 'api_id' e o 'api_hash'")
    print()
    print(f"{'='*55}\n")

    try:
        api_id = input("👉 Cole seu api_id: ").strip()
        api_hash = input("👉 Cole seu api_hash: ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\nCancelado.")
        sys.exit(0)

    if not api_id or not api_hash:
        print("❌ api_id e api_hash são obrigatórios.")
        sys.exit(1)

    CONFIG_FILE.write_text(json.dumps({"api_id": api_id, "api_hash": api_hash}, indent=2))
    print(f"\n✅ Credenciais salvas em {CONFIG_FILE.name}\n")

    return api_id, api_hash


def format_size(size_bytes: int) -> str:
    if size_bytes is None:
        return "tamanho desconhecido"
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def get_file_name(message) -> str | None:
    if not message.media:
        return None

    if isinstance(message.media, MessageMediaPhoto):
        return f"foto_{message.id}.jpg"

    if isinstance(message.media, MessageMediaDocument):
        doc = message.media.document
        if doc is None:
            return None

        for attr in doc.attributes:
            if isinstance(attr, DocumentAttributeFilename):
                return attr.file_name

        for attr in doc.attributes:
            if isinstance(attr, DocumentAttributeVideo):
                ext = "mp4"
                mime = getattr(doc, "mime_type", "")
                if "webm" in mime:
                    ext = "webm"
                elif "mkv" in mime:
                    ext = "mkv"
                return f"video_{message.id}.{ext}"

        mime = getattr(doc, "mime_type", "")
        ext = mime.split("/")[-1] if "/" in mime else "bin"
        return f"arquivo_{message.id}.{ext}"

    return None


def classify_media(message) -> str | None:
    if not message.media:
        return None

    if isinstance(message.media, MessageMediaPhoto):
        return "photo"

    if isinstance(message.media, MessageMediaDocument):
        doc = message.media.document
        if doc is None:
            return None

        for attr in doc.attributes:
            if isinstance(attr, DocumentAttributeVideo):
                return "video"

        return "document"

    return None


def progress_callback(current, total):
    percent = (current / total) * 100
    bar_length = 30
    filled = int(bar_length * current // total)
    bar = "█" * filled + "░" * (bar_length - filled)
    sys.stdout.write(f"\r  [{bar}] {percent:.1f}% ({format_size(current)}/{format_size(total)})")
    sys.stdout.flush()


async def list_groups(client: TelegramClient) -> list:
    groups = []
    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        if isinstance(entity, (Channel, Chat)):
            groups.append(dialog)
    return groups


async def get_group_media_stats(client: TelegramClient, group, media_types: list[str], limit: int | None) -> dict:
    total_size = 0
    counts = {"video": 0, "photo": 0, "document": 0}

    print(f"📊 Calculando tamanho do grupo '{group.name}'...", end="", flush=True)

    async for message in client.iter_messages(group.entity, limit=limit, reverse=True):
        media_type = classify_media(message)
        if media_type is None or media_type not in media_types:
            continue

        counts[media_type] += 1

        if isinstance(message.media, MessageMediaDocument) and message.media.document:
            total_size += message.media.document.size or 0

    print(" OK!\n")
    return {"total_size": total_size, "counts": counts}


async def download_media_from_group(client: TelegramClient, group, media_types: list[str], limit: int | None):
    group_name = group.name.replace("/", "_").replace("\\", "_").strip()
    download_dir = Path.cwd() / "downloads" / group_name
    download_dir.mkdir(parents=True, exist_ok=True)

    stats = await get_group_media_stats(client, group, media_types, limit)

    total_items = sum(stats["counts"].values())
    if total_items == 0:
        print("❌ Nenhuma mídia encontrada com os filtros selecionados.\n")
        return

    print(f"  {'='*45}")
    print(f"  RESUMO DO GRUPO")
    print(f"  {'='*45}")
    if stats["counts"]["video"]:
        print(f"  🎬 Vídeos:     {stats['counts']['video']}")
    if stats["counts"]["photo"]:
        print(f"  🖼  Fotos:      {stats['counts']['photo']}")
    if stats["counts"]["document"]:
        print(f"  📄 Documentos: {stats['counts']['document']}")
    print(f"  📦 Total:      {total_items} arquivos")
    print(f"  💾 Tamanho:    ~{format_size(stats['total_size'])} (sem contar fotos)")
    print(f"  {'='*45}\n")

    try:
        confirma = input("👉 Deseja continuar com o download? (s/n): ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print("\nCancelado.")
        return

    if confirma != "s":
        print("⏭  Download cancelado.\n")
        return

    print(f"\n📂 Salvando em: {download_dir}")
    print(f"🔍 Baixando mídia de '{group.name}'...\n")

    downloaded = 0
    skipped = 0
    errors = 0

    async for message in client.iter_messages(group.entity, limit=limit, reverse=True):
        media_type = classify_media(message)
        if media_type is None or media_type not in media_types:
            continue

        file_name = get_file_name(message)
        if file_name is None:
            continue

        file_path = download_dir / file_name

        if file_path.exists():
            skipped += 1
            continue

        size = None
        if isinstance(message.media, MessageMediaDocument) and message.media.document:
            size = message.media.document.size
        elif isinstance(message.media, MessageMediaPhoto):
            size = None

        size_str = f" ({format_size(size)})" if size else ""
        print(f"⬇  [{downloaded + skipped + 1}/{total_items}] [{media_type.upper()}] {file_name}{size_str}")

        try:
            await client.download_media(message, file=str(file_path), progress_callback=progress_callback)
            print()
            downloaded += 1
        except asyncio.CancelledError:
            if file_path.exists():
                file_path.unlink()
                print(f"\n  🗑  Arquivo incompleto removido: {file_name}")
            raise
        except Exception as e:
            if file_path.exists():
                file_path.unlink()
            print(f"\n  ❌ Erro: {e}")
            errors += 1

    print(f"\n{'='*50}")
    print(f"✅ Baixados: {downloaded}")
    print(f"⏭  Já existiam (pulados): {skipped}")
    if errors:
        print(f"❌ Erros: {errors}")
    print(f"📂 Pasta: {download_dir}")


async def main():
    api_id, api_hash = load_credentials()

    client = TelegramClient(SESSION_NAME, int(api_id), api_hash)
    await client.start()

    print(f"\n{'='*50}")
    print("  TELEGRAM GROUP DOWNLOADER")
    print(f"{'='*50}")

    me = await client.get_me()
    print(f"  Logado como: {me.first_name} (@{me.username or 'sem username'})")
    print(f"{'='*50}\n")

    while True:
        print("🔄 Carregando seus grupos/canais...\n")
        groups = await list_groups(client)

        if not groups:
            print("❌ Nenhum grupo ou canal encontrado.")
            break

        for i, g in enumerate(groups, 1):
            member_count = ""
            entity = g.entity
            if hasattr(entity, "participants_count") and entity.participants_count:
                member_count = f" ({entity.participants_count} membros)"
            tipo = "Canal" if isinstance(entity, Channel) and entity.broadcast else "Grupo"
            print(f"  {i:3d}. [{tipo}] {g.name}{member_count}")

        print(f"\n  0. Sair\n")

        try:
            choice = input("👉 Escolha o número do grupo: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nSaindo...")
            break

        if choice == "0":
            break

        try:
            idx = int(choice) - 1
            if idx < 0 or idx >= len(groups):
                print("❌ Número inválido.\n")
                continue
        except ValueError:
            print("❌ Digite um número válido.\n")
            continue

        selected = groups[idx]
        print(f"\n✅ Selecionado: {selected.name}\n")

        print("Que tipo de mídia deseja baixar?\n")
        for key, val in MEDIA_FILTERS.items():
            print(f"  {key}. {val['label']}")
        print()

        try:
            media_choice = input("👉 Escolha (1-4): ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nSaindo...")
            break

        if media_choice not in MEDIA_FILTERS:
            print("❌ Opção inválida.\n")
            continue

        media_types = MEDIA_FILTERS[media_choice]["types"]

        print("\nQuantas mensagens verificar? (quanto maior, mais tempo leva)")
        print("  - Digite um número (ex: 100, 500, 1000)")
        print("  - Ou 'todas' para verificar todas\n")

        try:
            limit_input = input("👉 Limite: ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\nSaindo...")
            break

        limit = None if limit_input == "todas" else int(limit_input) if limit_input.isdigit() else 100

        if limit and not limit_input.isdigit():
            print(f"  (valor inválido, usando padrão: {limit})")

        await download_media_from_group(client, selected, media_types, limit)

        print()
        try:
            cont = input("Deseja baixar de outro grupo? (s/n): ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            break

        if cont != "s":
            break

    await client.disconnect()
    print("\n👋 Até mais!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 Download interrompido. Execute novamente para continuar de onde parou.")
