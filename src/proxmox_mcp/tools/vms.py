"""Tools pour la gestion des VMs QEMU."""

from typing import Any, Literal

from proxmox_mcp.client import ProxmoxClient
from proxmox_mcp.exceptions import ErrorCode, InvalidStateError, ProxmoxError, VMNotFoundError
from proxmox_mcp.models import VMConfig, VMInfo
from proxmox_mcp.ssh_client import SSHClient


async def list_vms(client: ProxmoxClient, node: str | None = None) -> dict[str, Any]:
    """Liste toutes les VMs QEMU du cluster ou d'un nœud spécifique.

    Args:
        client: Client Proxmox
        node: Nom du nœud pour filtrer (optionnel)

    Returns:
        Dictionnaire avec la liste des VMs:
        {
            "success": True,
            "count": N,
            "data": [VMInfo, ...]
        }
    """
    try:
        vms = []

        if node:
            # Liste les VMs d'un nœud spécifique
            nodes_to_query = [node]
        else:
            # Récupérer tous les nœuds
            nodes_response = await client.get("/nodes")
            nodes_to_query = [n["node"] for n in nodes_response.get("data", [])]

        for node_name in nodes_to_query:
            response = await client.get(f"/nodes/{node_name}/qemu")
            vms_data = response.get("data", [])

            for vm_data in vms_data:
                vm = VMInfo(
                    vmid=vm_data.get("vmid", 0),
                    name=vm_data.get("name", ""),
                    status=vm_data.get("status", "unknown"),
                    node=node_name,
                    type="qemu",
                    cpu=vm_data.get("cpu", 0),
                    cpus=vm_data.get("cpus", 1),
                    mem=vm_data.get("mem", 0),
                    maxmem=vm_data.get("maxmem", 0),
                    disk=vm_data.get("disk", 0),
                    maxdisk=vm_data.get("maxdisk", 0),
                    uptime=vm_data.get("uptime", 0),
                    netin=vm_data.get("netin", 0),
                    netout=vm_data.get("netout", 0),
                )
                vms.append(vm.model_dump())

        return {
            "success": True,
            "count": len(vms),
            "data": vms,
        }

    except ProxmoxError as e:
        return e.to_dict()


async def get_vm_details(client: ProxmoxClient, node: str, vmid: int) -> dict[str, Any]:
    """Récupère la configuration détaillée d'une VM QEMU.

    Args:
        client: Client Proxmox
        node: Nom du nœud Proxmox
        vmid: ID de la VM

    Returns:
        Configuration complète de la VM incluant CPU, RAM, disques, réseau
    """
    try:
        # Récupérer la config
        config_response = await client.get(f"/nodes/{node}/qemu/{vmid}/config")
        config_data = config_response.get("data")

        if config_data is None:
            raise VMNotFoundError(vmid, node)

        # Récupérer le statut actuel
        status_response = await client.get(f"/nodes/{node}/qemu/{vmid}/status/current")
        status_data = status_response.get("data", {})

        # Extraire les disques et réseaux de la config
        networks = {}
        disks = {}

        for key, value in config_data.items():
            if key.startswith("net") and value:
                networks[key] = value
            elif key.startswith(("scsi", "virtio", "ide", "sata")) and value:
                if "media=cdrom" not in str(value):
                    disks[key] = value

        vm_config = VMConfig(
            vmid=vmid,
            name=config_data.get("name", ""),
            description=config_data.get("description", ""),
            cores=config_data.get("cores", 1),
            memory=config_data.get("memory", 512),
            balloon=config_data.get("balloon"),
            ostype=config_data.get("ostype", ""),
            boot=config_data.get("boot", ""),
            networks=networks,
            disks=disks,
            raw_config=config_data,
        )

        result = vm_config.model_dump()

        # Ajouter les infos de statut
        result["status"] = status_data.get("status", "unknown")
        result["cpu_usage"] = status_data.get("cpu", 0)
        result["mem_usage"] = status_data.get("mem", 0)
        result["uptime"] = status_data.get("uptime", 0)
        result["pid"] = status_data.get("pid")
        result["qmpstatus"] = status_data.get("qmpstatus", "")

        return {
            "success": True,
            "data": result,
        }

    except ProxmoxError as e:
        return e.to_dict()


async def _vm_action(
    client: ProxmoxClient,
    node: str,
    vmid: int,
    vm_type: Literal["qemu", "lxc"],
    action: str,
    action_name: str,
    allowed_states: list[str] | None = None,
    disallowed_states: list[str] | None = None,
) -> dict[str, Any]:
    """Effectue une action sur une VM ou conteneur.

    Args:
        client: Client Proxmox
        node: Nom du nœud
        vmid: ID de la VM/LXC
        vm_type: Type (qemu ou lxc)
        action: Action API (start, stop, shutdown, reboot)
        action_name: Nom de l'action pour les messages
        allowed_states: États autorisés pour l'action
        disallowed_states: États interdits pour l'action

    Returns:
        Résultat de l'action
    """
    try:
        # Vérifier l'état actuel
        status_path = f"/nodes/{node}/{vm_type}/{vmid}/status/current"
        status_response = await client.get(status_path)
        status_data = status_response.get("data")

        if status_data is None:
            raise VMNotFoundError(vmid, node)

        current_status = status_data.get("status", "unknown")

        # Vérifier les états autorisés/interdits
        if allowed_states and current_status not in allowed_states:
            raise InvalidStateError(
                f"Impossible de {action_name} la VM {vmid}: "
                f"état actuel '{current_status}', états autorisés: {allowed_states}"
            )

        if disallowed_states and current_status in disallowed_states:
            raise InvalidStateError(
                f"Impossible de {action_name} la VM {vmid}: état actuel '{current_status}'"
            )

        # Exécuter l'action
        action_path = f"/nodes/{node}/{vm_type}/{vmid}/status/{action}"
        response = await client.post(action_path)

        task_id = response.get("data", "")

        return {
            "success": True,
            "message": f"VM {vmid} {action_name} lancé avec succès",
            "task_id": task_id,
            "vmid": vmid,
            "node": node,
        }

    except ProxmoxError as e:
        return e.to_dict()


async def start_vm(
    client: ProxmoxClient,
    node: str,
    vmid: int,
    vm_type: Literal["qemu", "lxc"] = "qemu",
) -> dict[str, Any]:
    """Démarre une VM ou conteneur LXC.

    Args:
        client: Client Proxmox
        node: Nom du nœud Proxmox
        vmid: ID de la VM/LXC
        vm_type: Type (qemu ou lxc)

    Returns:
        Résultat de l'action avec task_id
    """
    return await _vm_action(
        client=client,
        node=node,
        vmid=vmid,
        vm_type=vm_type,
        action="start",
        action_name="démarrage",
        allowed_states=["stopped"],
    )


async def stop_vm(
    client: ProxmoxClient,
    node: str,
    vmid: int,
    vm_type: Literal["qemu", "lxc"] = "qemu",
) -> dict[str, Any]:
    """Arrête de force une VM ou conteneur LXC.

    Args:
        client: Client Proxmox
        node: Nom du nœud Proxmox
        vmid: ID de la VM/LXC
        vm_type: Type (qemu ou lxc)

    Returns:
        Résultat de l'action avec task_id
    """
    return await _vm_action(
        client=client,
        node=node,
        vmid=vmid,
        vm_type=vm_type,
        action="stop",
        action_name="arrêt forcé",
        disallowed_states=["stopped"],
    )


async def shutdown_vm(
    client: ProxmoxClient,
    node: str,
    vmid: int,
    vm_type: Literal["qemu", "lxc"] = "qemu",
) -> dict[str, Any]:
    """Arrête proprement une VM ou conteneur LXC (shutdown ACPI).

    Args:
        client: Client Proxmox
        node: Nom du nœud Proxmox
        vmid: ID de la VM/LXC
        vm_type: Type (qemu ou lxc)

    Returns:
        Résultat de l'action avec task_id
    """
    return await _vm_action(
        client=client,
        node=node,
        vmid=vmid,
        vm_type=vm_type,
        action="shutdown",
        action_name="arrêt gracieux",
        allowed_states=["running"],
    )


async def reboot_vm(
    client: ProxmoxClient,
    node: str,
    vmid: int,
    vm_type: Literal["qemu", "lxc"] = "qemu",
) -> dict[str, Any]:
    """Redémarre une VM ou conteneur LXC.

    Args:
        client: Client Proxmox
        node: Nom du nœud Proxmox
        vmid: ID de la VM/LXC
        vm_type: Type (qemu ou lxc)

    Returns:
        Résultat de l'action avec task_id
    """
    return await _vm_action(
        client=client,
        node=node,
        vmid=vmid,
        vm_type=vm_type,
        action="reboot",
        action_name="redémarrage",
        allowed_states=["running"],
    )


async def destroy_vm(
    client: ProxmoxClient,
    node: str,
    vmid: int,
    vm_type: Literal["qemu", "lxc"] = "qemu",
    purge: bool = True,
) -> dict[str, Any]:
    """Supprime définitivement une VM ou conteneur LXC.

    ATTENTION: Action destructive et irréversible!

    Args:
        client: Client Proxmox
        node: Nom du nœud Proxmox
        vmid: ID de la VM/LXC
        vm_type: Type (qemu ou lxc)
        purge: Purger également les jobs et configs liés

    Returns:
        Résultat de l'action avec task_id
    """
    try:
        # Vérifier que la VM existe et est arrêtée
        status_path = f"/nodes/{node}/{vm_type}/{vmid}/status/current"
        status_response = await client.get(status_path)
        status_data = status_response.get("data")

        if status_data is None:
            raise VMNotFoundError(vmid, node)

        current_status = status_data.get("status", "unknown")
        if current_status != "stopped":
            raise InvalidStateError(
                f"Impossible de supprimer la VM {vmid}: "
                f"elle doit être arrêtée (état actuel: {current_status})"
            )

        # Supprimer la VM
        delete_path = f"/nodes/{node}/{vm_type}/{vmid}"
        params = {}
        if purge:
            params["purge"] = 1
            params["destroy-unreferenced-disks"] = 1

        response = await client.delete(delete_path, params=params)
        task_id = response.get("data", "")

        return {
            "success": True,
            "message": f"VM {vmid} suppression lancée",
            "task_id": task_id,
            "vmid": vmid,
            "node": node,
            "warning": "Action irréversible - VM et disques supprimés définitivement",
        }

    except ProxmoxError as e:
        return e.to_dict()


# =============================================================================
# Guest Agent Tools
# =============================================================================


async def vm_exec(
    client: ProxmoxClient,
    node: str,
    vmid: int,
    command: str,
    input_data: str | None = None,
) -> dict[str, Any]:
    """Exécute une commande dans une VM via le QEMU Guest Agent.

    Note: L'API HTTP Proxmox exec ne supporte pas les arguments de commande.
    Pour des commandes complexes, le tool utilise l'API avec /bin/sh -c.

    Args:
        client: Client Proxmox
        node: Nom du nœud Proxmox
        vmid: ID de la VM
        command: Commande à exécuter (chemin absolu recommandé, ex: /usr/bin/hostname)
        input_data: Données d'entrée stdin (optionnel)

    Returns:
        PID du processus lancé pour récupérer le résultat avec vm_exec_status
    """
    try:
        # L'API Proxmox exec ne supporte pas les arguments via HTTP.
        # On passe directement la commande - elle doit être un chemin absolu
        # ou un binaire simple sans arguments.
        # Pour les commandes complexes, utiliser vm_exec_sync via SSH.
        params: dict[str, Any] = {"command": command}
        if input_data:
            params["input-data"] = input_data

        response = await client.post(
            f"/nodes/{node}/qemu/{vmid}/agent/exec",
            data=params,
        )

        data = response.get("data", {})

        return {
            "success": True,
            "pid": data.get("pid"),
            "vmid": vmid,
            "node": node,
            "message": f"Commande lancée, utilisez vm_exec_status avec pid={data.get('pid')} pour le résultat",
            "note": "Pour des commandes avec arguments, utilisez un chemin absolu simple (ex: /usr/bin/hostname)",
        }

    except ProxmoxError as e:
        return e.to_dict()
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "error_code": "GUEST_AGENT_ERROR",
        }


async def vm_exec_sync(
    ssh_client: SSHClient,
    node: str,
    vmid: int,
    command: str,
    timeout: int = 30,
) -> dict[str, Any]:
    """Exécute une commande dans une VM via SSH + qm guest exec (synchrone).

    Cette méthode supporte les commandes shell complètes avec arguments,
    pipes, redirections, etc. Le résultat est retourné directement.

    Args:
        ssh_client: Client SSH
        node: Nom du nœud Proxmox
        vmid: ID de la VM
        command: Commande shell à exécuter
        timeout: Timeout en secondes (défaut: 30)

    Returns:
        Résultat de la commande (stdout, stderr, exit_code)
    """
    try:
        import json as json_module

        # Échapper les guillemets dans la commande
        escaped_command = command.replace('"', '\\"')

        # Utiliser qm guest exec qui supporte les arguments via --
        ssh_command = f'qm guest exec {vmid} -- sh -c "{escaped_command}"'

        result = await ssh_client.execute(node, ssh_command, timeout=timeout)

        if result.exit_code != 0:
            return {
                "success": False,
                "error": result.stderr or f"Command failed with exit code {result.exit_code}",
                "error_code": "GUEST_EXEC_FAILED",
                "vmid": vmid,
            }

        # Parser le JSON retourné par qm guest exec
        try:
            output = json_module.loads(result.stdout)
            return {
                "success": True,
                "exited": output.get("exited", False),
                "exitcode": output.get("exitcode", 0),
                "stdout": output.get("out-data", ""),
                "stderr": output.get("err-data", ""),
                "vmid": vmid,
            }
        except json_module.JSONDecodeError:
            return {
                "success": True,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "vmid": vmid,
            }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "error_code": "GUEST_AGENT_ERROR",
        }


async def vm_exec_status(
    client: ProxmoxClient,
    node: str,
    vmid: int,
    pid: int,
) -> dict[str, Any]:
    """Récupère le résultat d'une commande exécutée via guest agent.

    Args:
        client: Client Proxmox
        node: Nom du nœud Proxmox
        vmid: ID de la VM
        pid: PID retourné par vm_exec

    Returns:
        Résultat de la commande (stdout, stderr, exit_code)
    """
    try:
        response = await client.get(
            f"/nodes/{node}/qemu/{vmid}/agent/exec-status",
            params={"pid": pid},
        )

        data = response.get("data", {})

        return {
            "success": True,
            "exited": data.get("exited", False),
            "exitcode": data.get("exitcode"),
            "stdout": data.get("out-data", ""),
            "stderr": data.get("err-data", ""),
            "signal": data.get("signal"),
            "vmid": vmid,
            "pid": pid,
        }

    except ProxmoxError as e:
        return e.to_dict()
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "error_code": "GUEST_AGENT_ERROR",
        }


async def vm_file_read(
    client: ProxmoxClient,
    node: str,
    vmid: int,
    path: str,
) -> dict[str, Any]:
    """Lit un fichier dans une VM via le QEMU Guest Agent.

    Args:
        client: Client Proxmox
        node: Nom du nœud Proxmox
        vmid: ID de la VM
        path: Chemin du fichier dans la VM

    Returns:
        Contenu du fichier
    """
    try:
        response = await client.get(
            f"/nodes/{node}/qemu/{vmid}/agent/file-read",
            params={"file": path},
        )

        data = response.get("data", {})
        import base64

        # Le contenu est encodé en base64
        content_b64 = data.get("content", "")
        try:
            content = base64.b64decode(content_b64).decode("utf-8")
        except Exception:
            content = content_b64

        return {
            "success": True,
            "path": path,
            "content": content,
            "truncated": data.get("truncated", False),
            "vmid": vmid,
        }

    except ProxmoxError as e:
        return e.to_dict()
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "error_code": "GUEST_AGENT_ERROR",
        }


# Chemins système critiques protégés contre l'écriture accidentelle
PROTECTED_PATHS = [
    "/etc/shadow",
    "/etc/passwd",
    "/etc/sudoers",
    "/etc/ssh/sshd_config",
    "/boot/",
    "/etc/fstab",
    "/etc/crypttab",
]


async def vm_file_write(
    client: ProxmoxClient,
    node: str,
    vmid: int,
    path: str,
    content: str,
    force: bool = False,
) -> dict[str, Any]:
    """Écrit un fichier dans une VM via le QEMU Guest Agent.

    Certains chemins système critiques sont protégés par défaut.
    Utilisez force=True pour écrire sur ces chemins (à vos risques).

    Args:
        client: Client Proxmox
        node: Nom du nœud Proxmox
        vmid: ID de la VM
        path: Chemin du fichier dans la VM
        content: Contenu à écrire
        force: Forcer l'écriture sur les chemins protégés (défaut: False)

    Returns:
        Confirmation de l'écriture
    """
    try:
        # Vérifier si le chemin est protégé
        if not force:
            for protected in PROTECTED_PATHS:
                if path == protected or path.startswith(protected):
                    return {
                        "success": False,
                        "error": f"Chemin protégé: {path}. Utilisez force=True pour écrire.",
                        "error_code": "PROTECTED_PATH",
                        "protected_paths": PROTECTED_PATHS,
                    }

        import base64

        # Encoder le contenu en base64
        content_b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")

        response = await client.post(
            f"/nodes/{node}/qemu/{vmid}/agent/file-write",
            data={
                "file": path,
                "content": content_b64,
            },
        )

        return {
            "success": True,
            "path": path,
            "vmid": vmid,
            "message": f"Fichier {path} écrit avec succès",
        }

    except ProxmoxError as e:
        return e.to_dict()
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "error_code": "GUEST_AGENT_ERROR",
        }


async def set_vm_config(
    client: ProxmoxClient,
    node: str,
    vmid: int,
    cores: int | None = None,
    sockets: int | None = None,
    memory: int | None = None,
    balloon: int | None = None,
    name: str | None = None,
    description: str | None = None,
    onboot: bool | None = None,
    cpulimit: float | None = None,
    cpuunits: int | None = None,
) -> dict[str, Any]:
    """Modifie la configuration d'une VM QEMU (CPU, RAM, etc.).

    Args:
        client: Client Proxmox
        node: Nom du noeud Proxmox
        vmid: ID de la VM
        cores: Nombre de coeurs CPU par socket
        sockets: Nombre de sockets CPU
        memory: RAM en MB
        balloon: RAM minimum pour le ballooning en MB (0 = desactive)
        name: Nom de la VM
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
        if sockets is not None:
            data["sockets"] = sockets
        if memory is not None:
            data["memory"] = memory
        if balloon is not None:
            data["balloon"] = balloon
        if name is not None:
            data["name"] = name
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

        await client.put(f"/nodes/{node}/qemu/{vmid}/config", data=data)

        return {
            "success": True,
            "message": f"Configuration de la VM {vmid} modifiee",
            "data": {
                "vmid": vmid,
                "node": node,
                "changes": data,
            },
        }

    except ProxmoxError as e:
        return e.to_dict()
