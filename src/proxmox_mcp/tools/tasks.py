"""Tools pour la gestion des tâches Proxmox."""

from typing import Any

from proxmox_mcp.client import ProxmoxClient
from proxmox_mcp.exceptions import ProxmoxError
from proxmox_mcp.models import TaskInfo, TaskStatus


async def list_tasks(
    client: ProxmoxClient,
    node: str,
    limit: int = 50,
    vmid: int | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    """Liste les tâches récentes d'un nœud Proxmox.

    Args:
        client: Client Proxmox
        node: Nom du nœud Proxmox
        limit: Nombre maximum de tâches à retourner (défaut: 50)
        vmid: Filtrer par ID de VM/LXC (optionnel)
        source: Filtrer par source (all, active, archive)

    Returns:
        Liste des tâches avec leurs statuts
    """
    try:
        params: dict[str, Any] = {"limit": limit}
        if vmid is not None:
            params["vmid"] = vmid
        if source:
            params["source"] = source

        response = await client.get(f"/nodes/{node}/tasks", params=params)
        tasks_data = response.get("data", [])

        tasks = []
        for task_data in tasks_data:
            task = TaskInfo(
                upid=task_data.get("upid", ""),
                node=task_data.get("node", node),
                type=task_data.get("type", ""),
                status=task_data.get("status", ""),
                user=task_data.get("user", ""),
                starttime=task_data.get("starttime", 0),
                endtime=task_data.get("endtime"),
                exitstatus=task_data.get("exitstatus"),
                id=task_data.get("id", ""),
            )
            tasks.append(task.model_dump())

        return {
            "success": True,
            "count": len(tasks),
            "data": tasks,
            "node": node,
        }

    except ProxmoxError as e:
        return e.to_dict()


async def get_task_status(
    client: ProxmoxClient,
    node: str,
    upid: str,
) -> dict[str, Any]:
    """Récupère le statut détaillé d'une tâche.

    Args:
        client: Client Proxmox
        node: Nom du nœud Proxmox
        upid: ID unique de la tâche (UPID)

    Returns:
        Statut détaillé de la tâche
    """
    try:
        response = await client.get(f"/nodes/{node}/tasks/{upid}/status")
        status_data = response.get("data", {})

        task_status = TaskStatus(
            upid=upid,
            node=status_data.get("node", node),
            type=status_data.get("type", ""),
            status=status_data.get("status", ""),
            exitstatus=status_data.get("exitstatus"),
            user=status_data.get("user", ""),
            starttime=status_data.get("starttime", 0),
            pid=status_data.get("pid"),
            pstart=status_data.get("pstart"),
        )

        result = task_status.model_dump()

        # Ajouter des infos sur la complétion
        result["is_running"] = task_status.status == "running"
        result["is_completed"] = task_status.status == "stopped"
        result["is_success"] = task_status.exitstatus == "OK" if task_status.exitstatus else None

        return {
            "success": True,
            "data": result,
        }

    except ProxmoxError as e:
        return e.to_dict()


async def get_task_log(
    client: ProxmoxClient,
    node: str,
    upid: str,
    start: int = 0,
    limit: int = 50,
) -> dict[str, Any]:
    """Récupère les logs d'une tâche.

    Args:
        client: Client Proxmox
        node: Nom du nœud Proxmox
        upid: ID unique de la tâche (UPID)
        start: Ligne de départ (défaut: 0)
        limit: Nombre de lignes à retourner (défaut: 50)

    Returns:
        Logs de la tâche
    """
    try:
        response = await client.get(
            f"/nodes/{node}/tasks/{upid}/log",
            params={"start": start, "limit": limit},
        )
        log_data = response.get("data", [])

        # Extraire les lignes de log
        log_lines = []
        for entry in log_data:
            if "t" in entry:
                log_lines.append(entry["t"])

        return {
            "success": True,
            "count": len(log_lines),
            "data": log_lines,
            "upid": upid,
            "node": node,
        }

    except ProxmoxError as e:
        return e.to_dict()
