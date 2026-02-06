"""Tools pour la gestion des conteneurs LXC."""

from typing import Any

from proxmox_mcp.client import ProxmoxClient
from proxmox_mcp.exceptions import ErrorCode, ProxmoxError, VMNotFoundError
from proxmox_mcp.models import VMConfig, VMInfo


async def list_containers(client: ProxmoxClient, node: str | None = None) -> dict[str, Any]:
    """Liste tous les conteneurs LXC du cluster ou d'un nœud spécifique.

    Args:
        client: Client Proxmox
        node: Nom du nœud pour filtrer (optionnel)

    Returns:
        Dictionnaire avec la liste des conteneurs:
        {
            "success": True,
            "count": N,
            "data": [VMInfo, ...]
        }
    """
    try:
        containers = []

        if node:
            nodes_to_query = [node]
        else:
            nodes_response = await client.get("/nodes")
            nodes_to_query = [n["node"] for n in nodes_response.get("data", [])]

        for node_name in nodes_to_query:
            response = await client.get(f"/nodes/{node_name}/lxc")
            lxc_data = response.get("data", [])

            for ct_data in lxc_data:
                container = VMInfo(
                    vmid=ct_data.get("vmid", 0),
                    name=ct_data.get("name", ""),
                    status=ct_data.get("status", "unknown"),
                    node=node_name,
                    type="lxc",
                    cpu=ct_data.get("cpu", 0),
                    cpus=ct_data.get("cpus", 1),
                    mem=ct_data.get("mem", 0),
                    maxmem=ct_data.get("maxmem", 0),
                    disk=ct_data.get("disk", 0),
                    maxdisk=ct_data.get("maxdisk", 0),
                    uptime=ct_data.get("uptime", 0),
                    netin=ct_data.get("netin", 0),
                    netout=ct_data.get("netout", 0),
                )
                containers.append(container.model_dump())

        return {
            "success": True,
            "count": len(containers),
            "data": containers,
        }

    except ProxmoxError as e:
        return e.to_dict()


async def get_container_details(client: ProxmoxClient, node: str, vmid: int) -> dict[str, Any]:
    """Récupère la configuration détaillée d'un conteneur LXC.

    Args:
        client: Client Proxmox
        node: Nom du nœud Proxmox
        vmid: ID du conteneur

    Returns:
        Configuration complète du conteneur incluant CPU, RAM, disques, réseau
    """
    try:
        # Récupérer la config
        config_response = await client.get(f"/nodes/{node}/lxc/{vmid}/config")
        config_data = config_response.get("data")

        if config_data is None:
            raise VMNotFoundError(vmid, node)

        # Récupérer le statut actuel
        status_response = await client.get(f"/nodes/{node}/lxc/{vmid}/status/current")
        status_data = status_response.get("data", {})

        # Extraire les réseaux et points de montage
        networks = {}
        mounts = {}

        for key, value in config_data.items():
            if key.startswith("net") and value:
                networks[key] = value
            elif key.startswith("mp") and value:
                mounts[key] = value

        # Rootfs est aussi un disque
        disks = {"rootfs": config_data.get("rootfs", "")}
        disks.update(mounts)

        container_config = VMConfig(
            vmid=vmid,
            name=config_data.get("hostname", ""),
            description=config_data.get("description", ""),
            cores=config_data.get("cores", 1),
            memory=config_data.get("memory", 512),
            ostype=config_data.get("ostype", ""),
            boot=config_data.get("onboot", ""),
            networks=networks,
            disks=disks,
            raw_config=config_data,
        )

        result = container_config.model_dump()

        # Ajouter les infos de statut
        result["status"] = status_data.get("status", "unknown")
        result["cpu_usage"] = status_data.get("cpu", 0)
        result["mem_usage"] = status_data.get("mem", 0)
        result["uptime"] = status_data.get("uptime", 0)
        result["pid"] = status_data.get("pid")

        # Infos spécifiques LXC
        result["arch"] = config_data.get("arch", "")
        result["ostemplate"] = config_data.get("ostemplate", "")
        result["unprivileged"] = config_data.get("unprivileged", 0) == 1

        return {
            "success": True,
            "data": result,
        }

    except ProxmoxError as e:
        return e.to_dict()


async def set_container_config(
    client: ProxmoxClient,
    node: str,
    vmid: int,
    cores: int | None = None,
    memory: int | None = None,
    swap: int | None = None,
    hostname: str | None = None,
    description: str | None = None,
    onboot: bool | None = None,
    cpulimit: float | None = None,
    cpuunits: int | None = None,
) -> dict[str, Any]:
    """Modifie la configuration d'un conteneur LXC (CPU, RAM, etc.).

    Args:
        client: Client Proxmox
        node: Nom du noeud Proxmox
        vmid: ID du conteneur
        cores: Nombre de coeurs CPU
        memory: RAM en MB
        swap: Swap en MB
        hostname: Nom d'hote du conteneur
        description: Description
        onboot: Demarrer au boot du noeud
        cpulimit: Limite CPU (0 = illimite)
        cpuunits: Poids CPU relatif (1024 = defaut)

    Returns:
        Resultat de la modification
    """
    try:
        data: dict[str, Any] = {}

        if cores is not None:
            data["cores"] = cores
        if memory is not None:
            data["memory"] = memory
        if swap is not None:
            data["swap"] = swap
        if hostname is not None:
            data["hostname"] = hostname
        if description is not None:
            data["description"] = description
        if onboot is not None:
            data["onboot"] = 1 if onboot else 0
        if cpulimit is not None:
            data["cpulimit"] = cpulimit
        if cpuunits is not None:
            data["cpuunits"] = cpuunits

        if not data:
            return {
                "success": False,
                "error": "Aucune modification specifiee",
                "error_code": ErrorCode.NO_CHANGES.value,
            }

        await client.put(f"/nodes/{node}/lxc/{vmid}/config", data=data)

        return {
            "success": True,
            "message": f"Configuration du conteneur {vmid} modifiee",
            "data": {
                "vmid": vmid,
                "node": node,
                "changes": data,
            },
        }

    except ProxmoxError as e:
        return e.to_dict()
