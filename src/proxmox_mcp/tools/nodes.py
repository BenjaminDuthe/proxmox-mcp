"""Tools pour la gestion des nœuds Proxmox."""

from typing import Any

from proxmox_mcp.client import ProxmoxClient
from proxmox_mcp.exceptions import NodeNotFoundError, ProxmoxError
from proxmox_mcp.models import NodeInfo


async def list_nodes(client: ProxmoxClient) -> dict[str, Any]:
    """Liste tous les nœuds du cluster Proxmox avec leur statut.

    Args:
        client: Client Proxmox

    Returns:
        Dictionnaire avec la liste des nœuds:
        {
            "success": True,
            "count": N,
            "data": [NodeInfo, ...]
        }
    """
    try:
        response = await client.get("/nodes")
        nodes_data = response.get("data", [])

        nodes = []
        for node_data in nodes_data:
            node = NodeInfo(
                node=node_data.get("node", ""),
                status=node_data.get("status", "unknown"),
                cpu=node_data.get("cpu", 0),
                maxcpu=node_data.get("maxcpu", 0),
                mem=node_data.get("mem", 0),
                maxmem=node_data.get("maxmem", 0),
                disk=node_data.get("disk", 0),
                maxdisk=node_data.get("maxdisk", 0),
                uptime=node_data.get("uptime", 0),
            )
            nodes.append(node.model_dump())

        return {
            "success": True,
            "count": len(nodes),
            "data": nodes,
        }

    except ProxmoxError as e:
        return e.to_dict()


async def get_node_status(client: ProxmoxClient, node: str) -> dict[str, Any]:
    """Récupère les métriques détaillées d'un nœud Proxmox.

    Args:
        client: Client Proxmox
        node: Nom du nœud

    Returns:
        Dictionnaire avec les informations détaillées du nœud:
        {
            "success": True,
            "data": {
                "node": "pve",
                "status": "online",
                "cpu": 0.15,
                "cpu_percent": 15.0,
                ...
            }
        }
    """
    try:
        response = await client.get(f"/nodes/{node}/status")
        data = response.get("data")

        if data is None:
            raise NodeNotFoundError(node)

        # Construire les infos du nœud
        node_info = NodeInfo(
            node=node,
            status="online",  # Si on peut récupérer le status, le nœud est online
            cpu=data.get("cpu", 0),
            maxcpu=data.get("cpuinfo", {}).get("cpus", 0),
            mem=data.get("memory", {}).get("used", 0),
            maxmem=data.get("memory", {}).get("total", 0),
            disk=data.get("rootfs", {}).get("used", 0),
            maxdisk=data.get("rootfs", {}).get("total", 0),
            uptime=data.get("uptime", 0),
        )

        result = node_info.model_dump()
        # Ajouter les pourcentages calculés
        result["cpu_percent"] = node_info.cpu_percent
        result["mem_percent"] = node_info.mem_percent
        result["disk_percent"] = node_info.disk_percent

        # Ajouter des infos supplémentaires si disponibles
        if "cpuinfo" in data:
            result["cpu_model"] = data["cpuinfo"].get("model", "")
            result["cpu_cores"] = data["cpuinfo"].get("cores", 0)
            result["cpu_sockets"] = data["cpuinfo"].get("sockets", 0)

        if "kversion" in data:
            result["kernel_version"] = data["kversion"]

        if "pveversion" in data:
            result["pve_version"] = data["pveversion"]

        return {
            "success": True,
            "data": result,
        }

    except ProxmoxError as e:
        return e.to_dict()
