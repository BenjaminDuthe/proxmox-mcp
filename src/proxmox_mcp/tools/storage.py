"""Tools pour la gestion du stockage Proxmox."""

from typing import Any

from proxmox_mcp.client import ProxmoxClient
from proxmox_mcp.exceptions import ProxmoxError, StorageNotFoundError
from proxmox_mcp.models import StorageContent, StorageInfo


async def list_storage(client: ProxmoxClient, node: str) -> dict[str, Any]:
    """Liste les pools de stockage d'un nœud Proxmox.

    Args:
        client: Client Proxmox
        node: Nom du nœud Proxmox

    Returns:
        Liste des storages avec leurs métriques d'utilisation
    """
    try:
        response = await client.get(f"/nodes/{node}/storage")
        storage_data = response.get("data", [])

        storages = []
        for stor_data in storage_data:
            storage = StorageInfo(
                storage=stor_data.get("storage", ""),
                type=stor_data.get("type", ""),
                content=stor_data.get("content", ""),
                active=stor_data.get("active", 1) == 1,
                enabled=stor_data.get("enabled", 1) == 1,
                shared=stor_data.get("shared", 0) == 1,
                used=stor_data.get("used", 0),
                avail=stor_data.get("avail", 0),
                total=stor_data.get("total", 0),
            )
            result = storage.model_dump()
            result["used_percent"] = storage.used_percent
            storages.append(result)

        return {
            "success": True,
            "count": len(storages),
            "data": storages,
            "node": node,
        }

    except ProxmoxError as e:
        return e.to_dict()


async def get_storage_content(
    client: ProxmoxClient,
    node: str,
    storage: str,
    content_type: str | None = None,
) -> dict[str, Any]:
    """Récupère le contenu d'un pool de stockage.

    Args:
        client: Client Proxmox
        node: Nom du nœud Proxmox
        storage: Nom du storage
        content_type: Filtrer par type (images, iso, vztmpl, backup, etc.)

    Returns:
        Liste des volumes/fichiers dans le storage
    """
    try:
        params = {}
        if content_type:
            params["content"] = content_type

        response = await client.get(
            f"/nodes/{node}/storage/{storage}/content",
            params=params if params else None,
        )
        content_data = response.get("data")

        if content_data is None:
            raise StorageNotFoundError(storage, node)

        contents = []
        for item_data in content_data:
            content = StorageContent(
                volid=item_data.get("volid", ""),
                format=item_data.get("format", ""),
                size=item_data.get("size", 0),
                ctime=item_data.get("ctime"),
                vmid=item_data.get("vmid"),
                content=item_data.get("content", ""),
            )
            contents.append(content.model_dump())

        return {
            "success": True,
            "count": len(contents),
            "data": contents,
            "node": node,
            "storage": storage,
        }

    except ProxmoxError as e:
        return e.to_dict()


async def get_storage_status(
    client: ProxmoxClient,
    node: str,
    storage: str,
) -> dict[str, Any]:
    """Récupère le statut et l'utilisation d'un storage.

    Args:
        client: Client Proxmox
        node: Nom du nœud Proxmox
        storage: Nom du storage

    Returns:
        Informations détaillées sur le storage
    """
    try:
        response = await client.get(f"/nodes/{node}/storage/{storage}/status")
        status_data = response.get("data")

        if status_data is None:
            raise StorageNotFoundError(storage, node)

        storage_info = StorageInfo(
            storage=storage,
            type=status_data.get("type", ""),
            content=status_data.get("content", ""),
            active=status_data.get("active", 1) == 1,
            enabled=status_data.get("enabled", 1) == 1,
            shared=status_data.get("shared", 0) == 1,
            used=status_data.get("used", 0),
            avail=status_data.get("avail", 0),
            total=status_data.get("total", 0),
        )

        result = storage_info.model_dump()
        result["used_percent"] = storage_info.used_percent

        return {
            "success": True,
            "data": result,
            "node": node,
        }

    except ProxmoxError as e:
        return e.to_dict()
