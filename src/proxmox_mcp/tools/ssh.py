"""Tools SSH pour l'administration directe des nœuds Proxmox."""

from typing import Any

from proxmox_mcp.exceptions import ProxmoxError, SSHError
from proxmox_mcp.ssh_client import SSHClient


async def ssh_execute(
    ssh_client: SSHClient,
    node: str,
    command: str,
    timeout: int = 30,
) -> dict[str, Any]:
    """Exécute une commande SSH sur un nœud Proxmox.

    Args:
        ssh_client: Client SSH
        node: Nom du nœud Proxmox
        command: Commande à exécuter
        timeout: Timeout en secondes (défaut: 30)

    Returns:
        Résultat avec stdout, stderr, exit_code:
        {
            "success": True,
            "data": {
                "command": "hostname",
                "exit_code": 0,
                "stdout": "pve1\\n",
                "stderr": "",
                "duration_ms": 45
            }
        }
    """
    try:
        result = await ssh_client.execute(
            node=node,
            command=command,
            timeout=timeout,
            check_exit_code=False,  # On retourne le résultat même si erreur
        )

        return {
            "success": result["exit_code"] == 0,
            "data": result,
        }

    except SSHError as e:
        return e.to_dict()
    except ProxmoxError as e:
        return e.to_dict()


async def ssh_read_file(
    ssh_client: SSHClient,
    node: str,
    path: str,
    max_size: int = 1048576,
) -> dict[str, Any]:
    """Lit un fichier distant sur un nœud Proxmox.

    Args:
        ssh_client: Client SSH
        node: Nom du nœud Proxmox
        path: Chemin absolu du fichier
        max_size: Taille max en bytes (défaut: 1MB)

    Returns:
        Contenu du fichier:
        {
            "success": True,
            "data": {
                "path": "/etc/apt/sources.list",
                "exists": True,
                "size": 1234,
                "content": "..."
            }
        }
    """
    try:
        result = await ssh_client.read_file(
            node=node,
            path=path,
            max_size=max_size,
        )

        return {
            "success": True,
            "data": result,
        }

    except SSHError as e:
        return e.to_dict()
    except ProxmoxError as e:
        return e.to_dict()


async def ssh_write_file(
    ssh_client: SSHClient,
    node: str,
    path: str,
    content: str,
    backup: bool = True,
    mode: str = "0644",
) -> dict[str, Any]:
    """Écrit un fichier distant sur un nœud Proxmox.

    ATTENTION: Crée un backup automatique par défaut.

    Args:
        ssh_client: Client SSH
        node: Nom du nœud Proxmox
        path: Chemin absolu du fichier
        content: Contenu à écrire
        backup: Créer un backup .bak (défaut: True)
        mode: Permissions du fichier (défaut: "0644")

    Returns:
        Résultat de l'écriture:
        {
            "success": True,
            "data": {
                "path": "/etc/apt/sources.list.d/pve.list",
                "backup_path": "/etc/apt/sources.list.d/pve.list.bak.20240115_143022",
                "size": 89
            }
        }
    """
    try:
        result = await ssh_client.write_file(
            node=node,
            path=path,
            content=content,
            backup=backup,
            mode=mode,
        )

        return {
            "success": True,
            "message": f"Fichier '{path}' écrit avec succès",
            "data": result,
        }

    except SSHError as e:
        return e.to_dict()
    except ProxmoxError as e:
        return e.to_dict()


async def fix_apt_repos(
    ssh_client: SSHClient,
    node: str,
    disable_enterprise: bool = True,
    enable_no_subscription: bool = True,
) -> dict[str, Any]:
    """Corrige les dépôts APT Proxmox pour les installations sans souscription.

    Cette fonction:
    1. Désactive le dépôt enterprise (requiert souscription payante)
    2. Active le dépôt no-subscription (community)
    3. Crée des backups des fichiers modifiés

    Args:
        ssh_client: Client SSH
        node: Nom du nœud Proxmox
        disable_enterprise: Désactiver pve-enterprise.list (défaut: True)
        enable_no_subscription: Activer pve-no-subscription (défaut: True)

    Returns:
        Résultat des modifications:
        {
            "success": True,
            "message": "Dépôts APT configurés",
            "data": {
                "changes": [...],
                "backups": [...],
                "apt_update_required": True
            }
        }
    """
    try:
        changes = []
        backups = []

        # 1. Désactiver le dépôt enterprise
        if disable_enterprise:
            enterprise_file = "/etc/apt/sources.list.d/pve-enterprise.list"

            # Vérifier si le fichier existe
            check = await ssh_client.execute(
                node,
                f'test -f "{enterprise_file}" && echo "EXISTS"',
                check_exit_code=False,
            )

            if "EXISTS" in check["stdout"]:
                # Lire le contenu actuel
                content_result = await ssh_client.read_file(node, enterprise_file)
                current_content = content_result["content"]

                # Vérifier si déjà commenté
                lines = current_content.strip().splitlines()
                has_active_repo = any(
                    line.strip() and not line.strip().startswith("#")
                    for line in lines
                )

                if has_active_repo:
                    # Commenter toutes les lignes non commentées
                    new_lines = []
                    for line in lines:
                        if line.strip() and not line.strip().startswith("#"):
                            new_lines.append(f"# {line}")
                        else:
                            new_lines.append(line)

                    new_content = "# Disabled by proxmox-mcp fix_apt_repos\n"
                    new_content += "\n".join(new_lines)

                    result = await ssh_client.write_file(
                        node,
                        enterprise_file,
                        new_content,
                        backup=True,
                    )
                    changes.append(f"Dépôt enterprise désactivé: {enterprise_file}")
                    if result.get("backup_path"):
                        backups.append(result["backup_path"])

        # 2. Activer le dépôt no-subscription
        if enable_no_subscription:
            no_sub_file = "/etc/apt/sources.list.d/pve-no-subscription.list"

            # Détecter la version Proxmox pour le bon nom de release
            version_result = await ssh_client.execute(
                node,
                "grep 'VERSION_CODENAME' /etc/os-release | cut -d'=' -f2",
                check_exit_code=False,
            )
            codename = version_result["stdout"].strip() or "bookworm"

            no_sub_content = f"""# Proxmox VE No-Subscription Repository
# Added by proxmox-mcp fix_apt_repos
deb http://download.proxmox.com/debian/pve {codename} pve-no-subscription
"""

            # Vérifier si déjà configuré
            check = await ssh_client.execute(
                node,
                f'test -f "{no_sub_file}" && grep -q "pve-no-subscription" "{no_sub_file}" && echo "CONFIGURED"',
                check_exit_code=False,
            )

            if "CONFIGURED" not in check["stdout"]:
                result = await ssh_client.write_file(
                    node,
                    no_sub_file,
                    no_sub_content,
                    backup=True,
                )
                changes.append(f"Dépôt no-subscription activé: {no_sub_file}")
                if result.get("backup_path"):
                    backups.append(result["backup_path"])

        return {
            "success": True,
            "message": "Dépôts APT configurés pour Proxmox sans souscription",
            "data": {
                "changes": changes,
                "backups": backups,
                "apt_update_required": len(changes) > 0,
                "next_step": "Exécuter 'apt update' pour appliquer les changements"
                if changes
                else None,
            },
        }

    except SSHError as e:
        return e.to_dict()
    except ProxmoxError as e:
        return e.to_dict()
