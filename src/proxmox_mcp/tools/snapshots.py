"""Tools pour la gestion des snapshots."""

from typing import Any, Literal

from proxmox_mcp.client import ProxmoxClient
from proxmox_mcp.exceptions import ProxmoxError, SnapshotNotFoundError, VMNotFoundError
from proxmox_mcp.models import SnapshotInfo


async def list_snapshots(
    client: ProxmoxClient,
    node: str,
    vmid: int,
    vm_type: Literal["qemu", "lxc"] = "qemu",
) -> dict[str, Any]:
    """Liste les snapshots d'une VM ou conteneur.

    Args:
        client: Client Proxmox
        node: Nom du nœud Proxmox
        vmid: ID de la VM/LXC
        vm_type: Type (qemu ou lxc)

    Returns:
        Liste des snapshots avec leurs métadonnées
    """
    try:
        response = await client.get(f"/nodes/{node}/{vm_type}/{vmid}/snapshot")
        snapshots_data = response.get("data")

        if snapshots_data is None:
            raise VMNotFoundError(vmid, node)

        snapshots = []
        for snap_data in snapshots_data:
            # Ignorer le snapshot "current" qui représente l'état actuel
            if snap_data.get("name") == "current":
                continue

            snapshot = SnapshotInfo(
                name=snap_data.get("name", ""),
                description=snap_data.get("description"),
                snaptime=snap_data.get("snaptime"),
                parent=snap_data.get("parent"),
                vmstate=snap_data.get("vmstate", False),
            )
            snapshots.append(snapshot.model_dump())

        return {
            "success": True,
            "count": len(snapshots),
            "data": snapshots,
            "vmid": vmid,
            "node": node,
            "type": vm_type,
        }

    except ProxmoxError as e:
        return e.to_dict()


async def create_snapshot(
    client: ProxmoxClient,
    node: str,
    vmid: int,
    vm_type: Literal["qemu", "lxc"],
    name: str,
    description: str | None = None,
    vmstate: bool = False,
) -> dict[str, Any]:
    """Crée un snapshot d'une VM ou conteneur.

    Args:
        client: Client Proxmox
        node: Nom du nœud Proxmox
        vmid: ID de la VM/LXC
        vm_type: Type (qemu ou lxc)
        name: Nom du snapshot
        description: Description optionnelle
        vmstate: Inclure l'état RAM (VM QEMU uniquement)

    Returns:
        Résultat de la création avec task_id
    """
    try:
        # Vérifier que la VM existe
        status_response = await client.get(
            f"/nodes/{node}/{vm_type}/{vmid}/status/current"
        )
        if status_response.get("data") is None:
            raise VMNotFoundError(vmid, node)

        # Préparer les données
        data: dict[str, Any] = {"snapname": name}
        if description:
            data["description"] = description
        if vmstate and vm_type == "qemu":
            data["vmstate"] = 1

        # Créer le snapshot
        response = await client.post(
            f"/nodes/{node}/{vm_type}/{vmid}/snapshot",
            data=data,
        )

        task_id = response.get("data", "")

        return {
            "success": True,
            "message": f"Snapshot '{name}' création lancée pour {vm_type} {vmid}",
            "task_id": task_id,
            "vmid": vmid,
            "node": node,
            "snapshot_name": name,
        }

    except ProxmoxError as e:
        return e.to_dict()


async def delete_snapshot(
    client: ProxmoxClient,
    node: str,
    vmid: int,
    vm_type: Literal["qemu", "lxc"],
    snapname: str,
) -> dict[str, Any]:
    """Supprime un snapshot d'une VM ou conteneur.

    Args:
        client: Client Proxmox
        node: Nom du nœud Proxmox
        vmid: ID de la VM/LXC
        vm_type: Type (qemu ou lxc)
        snapname: Nom du snapshot à supprimer

    Returns:
        Résultat de la suppression avec task_id
    """
    try:
        # Vérifier que le snapshot existe
        snapshots_response = await client.get(
            f"/nodes/{node}/{vm_type}/{vmid}/snapshot"
        )
        snapshots_data = snapshots_response.get("data", [])

        snapshot_exists = any(
            s.get("name") == snapname for s in snapshots_data if s.get("name") != "current"
        )

        if not snapshot_exists:
            raise SnapshotNotFoundError(snapname, vmid)

        # Supprimer le snapshot
        response = await client.delete(
            f"/nodes/{node}/{vm_type}/{vmid}/snapshot/{snapname}"
        )

        task_id = response.get("data", "")

        return {
            "success": True,
            "message": f"Snapshot '{snapname}' suppression lancée",
            "task_id": task_id,
            "vmid": vmid,
            "node": node,
            "snapshot_name": snapname,
        }

    except ProxmoxError as e:
        return e.to_dict()


async def rollback_snapshot(
    client: ProxmoxClient,
    node: str,
    vmid: int,
    vm_type: Literal["qemu", "lxc"],
    snapname: str,
) -> dict[str, Any]:
    """Restaure une VM ou conteneur vers un snapshot.

    ATTENTION: L'état actuel non sauvegardé sera perdu!

    Args:
        client: Client Proxmox
        node: Nom du nœud Proxmox
        vmid: ID de la VM/LXC
        vm_type: Type (qemu ou lxc)
        snapname: Nom du snapshot à restaurer

    Returns:
        Résultat du rollback avec task_id
    """
    try:
        # Vérifier que le snapshot existe
        snapshots_response = await client.get(
            f"/nodes/{node}/{vm_type}/{vmid}/snapshot"
        )
        snapshots_data = snapshots_response.get("data", [])

        snapshot_exists = any(
            s.get("name") == snapname for s in snapshots_data if s.get("name") != "current"
        )

        if not snapshot_exists:
            raise SnapshotNotFoundError(snapname, vmid)

        # Effectuer le rollback
        response = await client.post(
            f"/nodes/{node}/{vm_type}/{vmid}/snapshot/{snapname}/rollback"
        )

        task_id = response.get("data", "")

        return {
            "success": True,
            "message": f"Rollback vers snapshot '{snapname}' lancé",
            "task_id": task_id,
            "vmid": vmid,
            "node": node,
            "snapshot_name": snapname,
            "warning": "L'état actuel non sauvegardé a été perdu",
        }

    except ProxmoxError as e:
        return e.to_dict()
