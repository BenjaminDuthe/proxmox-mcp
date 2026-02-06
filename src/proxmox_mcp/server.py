"""Serveur MCP pour Proxmox VE.

Point d'entrée principal du serveur MCP qui expose les tools
pour interagir avec l'infrastructure Proxmox.
"""

import asyncio
import json
import logging
import sys
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from proxmox_mcp.client import ProxmoxClient, set_client
from proxmox_mcp.config import get_config
from proxmox_mcp.ssh_client import SSHClient, set_ssh_client
from proxmox_mcp.tools import (
    containers,
    nodes,
    snapshots,
    ssh,
    storage,
    tasks,
    users,
    vms,
)

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("proxmox-mcp")

# Créer le serveur MCP
server = Server("proxmox-mcp")

# Instances globales des clients
_client: ProxmoxClient | None = None
_ssh_client: SSHClient | None = None


def _get_client() -> ProxmoxClient:
    """Retourne le client Proxmox global."""
    if _client is None:
        raise RuntimeError("Client Proxmox non initialisé")
    return _client


def _get_ssh_client() -> SSHClient:
    """Retourne le client SSH global."""
    if _ssh_client is None:
        raise RuntimeError("Client SSH non initialisé ou SSH désactivé")
    return _ssh_client


# =============================================================================
# Définition des tools
# =============================================================================

TOOLS = [
    # Nœuds
    Tool(
        name="list_nodes",
        description="Liste tous les nœuds du cluster Proxmox avec leur statut, "
        "utilisation CPU/RAM/disque et uptime",
        inputSchema={
            "type": "object",
            "properties": {},
            "required": [],
        },
    ),
    Tool(
        name="get_node_status",
        description="Récupère les métriques détaillées d'un nœud Proxmox: "
        "CPU, RAM, disque, version PVE, kernel",
        inputSchema={
            "type": "object",
            "properties": {
                "node": {
                    "type": "string",
                    "description": "Nom du nœud Proxmox",
                }
            },
            "required": ["node"],
        },
    ),
    # VMs QEMU
    Tool(
        name="list_vms",
        description="Liste toutes les VMs QEMU du cluster ou d'un nœud spécifique",
        inputSchema={
            "type": "object",
            "properties": {
                "node": {
                    "type": "string",
                    "description": "Nom du nœud pour filtrer (optionnel)",
                }
            },
            "required": [],
        },
    ),
    Tool(
        name="get_vm_details",
        description="Récupère la configuration complète d'une VM QEMU: "
        "CPU, RAM, disques, réseau, statut",
        inputSchema={
            "type": "object",
            "properties": {
                "node": {
                    "type": "string",
                    "description": "Nom du nœud Proxmox",
                },
                "vmid": {
                    "type": "integer",
                    "description": "ID de la VM",
                },
            },
            "required": ["node", "vmid"],
        },
    ),
    Tool(
        name="start_vm",
        description="Démarre une VM QEMU ou un conteneur LXC",
        inputSchema={
            "type": "object",
            "properties": {
                "node": {
                    "type": "string",
                    "description": "Nom du nœud Proxmox",
                },
                "vmid": {
                    "type": "integer",
                    "description": "ID de la VM/LXC",
                },
                "type": {
                    "type": "string",
                    "enum": ["qemu", "lxc"],
                    "description": "Type: qemu (VM) ou lxc (conteneur)",
                    "default": "qemu",
                },
            },
            "required": ["node", "vmid"],
        },
    ),
    Tool(
        name="stop_vm",
        description="Arrête de force une VM QEMU ou un conteneur LXC (équivalent à couper l'alimentation)",
        inputSchema={
            "type": "object",
            "properties": {
                "node": {
                    "type": "string",
                    "description": "Nom du nœud Proxmox",
                },
                "vmid": {
                    "type": "integer",
                    "description": "ID de la VM/LXC",
                },
                "type": {
                    "type": "string",
                    "enum": ["qemu", "lxc"],
                    "description": "Type: qemu (VM) ou lxc (conteneur)",
                    "default": "qemu",
                },
            },
            "required": ["node", "vmid"],
        },
    ),
    Tool(
        name="shutdown_vm",
        description="Arrête proprement une VM QEMU ou conteneur LXC via ACPI/signal shutdown",
        inputSchema={
            "type": "object",
            "properties": {
                "node": {
                    "type": "string",
                    "description": "Nom du nœud Proxmox",
                },
                "vmid": {
                    "type": "integer",
                    "description": "ID de la VM/LXC",
                },
                "type": {
                    "type": "string",
                    "enum": ["qemu", "lxc"],
                    "description": "Type: qemu (VM) ou lxc (conteneur)",
                    "default": "qemu",
                },
            },
            "required": ["node", "vmid"],
        },
    ),
    Tool(
        name="reboot_vm",
        description="Redémarre une VM QEMU ou conteneur LXC",
        inputSchema={
            "type": "object",
            "properties": {
                "node": {
                    "type": "string",
                    "description": "Nom du nœud Proxmox",
                },
                "vmid": {
                    "type": "integer",
                    "description": "ID de la VM/LXC",
                },
                "type": {
                    "type": "string",
                    "enum": ["qemu", "lxc"],
                    "description": "Type: qemu (VM) ou lxc (conteneur)",
                    "default": "qemu",
                },
            },
            "required": ["node", "vmid"],
        },
    ),
    Tool(
        name="destroy_vm",
        description="DANGER: Supprime définitivement une VM QEMU ou conteneur LXC et ses disques. "
        "Action irréversible!",
        inputSchema={
            "type": "object",
            "properties": {
                "node": {
                    "type": "string",
                    "description": "Nom du nœud Proxmox",
                },
                "vmid": {
                    "type": "integer",
                    "description": "ID de la VM/LXC",
                },
                "type": {
                    "type": "string",
                    "enum": ["qemu", "lxc"],
                    "description": "Type: qemu (VM) ou lxc (conteneur)",
                    "default": "qemu",
                },
                "purge": {
                    "type": "boolean",
                    "description": "Purger les jobs et configs liés",
                    "default": True,
                },
            },
            "required": ["node", "vmid"],
        },
    ),
    Tool(
        name="set_vm_config",
        description="Modifie la configuration d'une VM QEMU (CPU, RAM, nom, etc.)",
        inputSchema={
            "type": "object",
            "properties": {
                "node": {
                    "type": "string",
                    "description": "Nom du noeud Proxmox",
                },
                "vmid": {
                    "type": "integer",
                    "description": "ID de la VM",
                },
                "cores": {
                    "type": "integer",
                    "description": "Nombre de coeurs CPU par socket",
                },
                "sockets": {
                    "type": "integer",
                    "description": "Nombre de sockets CPU",
                },
                "memory": {
                    "type": "integer",
                    "description": "RAM en MB",
                },
                "balloon": {
                    "type": "integer",
                    "description": "RAM minimum pour le ballooning en MB (0 = desactive)",
                },
                "name": {
                    "type": "string",
                    "description": "Nom de la VM",
                },
                "description": {
                    "type": "string",
                    "description": "Description",
                },
                "onboot": {
                    "type": "boolean",
                    "description": "Demarrer au boot du noeud",
                },
                "cpulimit": {
                    "type": "number",
                    "description": "Limite CPU (0 = illimite)",
                },
                "cpuunits": {
                    "type": "integer",
                    "description": "Poids CPU relatif (1024 = defaut)",
                },
            },
            "required": ["node", "vmid"],
        },
    ),
    # Guest Agent
    Tool(
        name="vm_exec",
        description="Exécute une commande dans une VM via le QEMU Guest Agent. "
        "Retourne un PID à utiliser avec vm_exec_status pour obtenir le résultat.",
        inputSchema={
            "type": "object",
            "properties": {
                "node": {
                    "type": "string",
                    "description": "Nom du nœud Proxmox",
                },
                "vmid": {
                    "type": "integer",
                    "description": "ID de la VM",
                },
                "command": {
                    "type": "string",
                    "description": "Commande à exécuter dans la VM",
                },
            },
            "required": ["node", "vmid", "command"],
        },
    ),
    Tool(
        name="vm_exec_status",
        description="Récupère le résultat d'une commande exécutée via guest agent (stdout, stderr, exit code)",
        inputSchema={
            "type": "object",
            "properties": {
                "node": {
                    "type": "string",
                    "description": "Nom du nœud Proxmox",
                },
                "vmid": {
                    "type": "integer",
                    "description": "ID de la VM",
                },
                "pid": {
                    "type": "integer",
                    "description": "PID retourné par vm_exec",
                },
            },
            "required": ["node", "vmid", "pid"],
        },
    ),
    Tool(
        name="vm_exec_sync",
        description="Exécute une commande shell dans une VM et retourne le résultat directement. "
        "Supporte les commandes complexes avec arguments, pipes, etc. Nécessite SSH.",
        inputSchema={
            "type": "object",
            "properties": {
                "node": {
                    "type": "string",
                    "description": "Nom du nœud Proxmox",
                },
                "vmid": {
                    "type": "integer",
                    "description": "ID de la VM",
                },
                "command": {
                    "type": "string",
                    "description": "Commande shell à exécuter (supporte pipes, redirections, etc.)",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout en secondes (défaut: 30)",
                    "default": 30,
                },
            },
            "required": ["node", "vmid", "command"],
        },
    ),
    Tool(
        name="vm_file_read",
        description="Lit un fichier dans une VM via le QEMU Guest Agent",
        inputSchema={
            "type": "object",
            "properties": {
                "node": {
                    "type": "string",
                    "description": "Nom du nœud Proxmox",
                },
                "vmid": {
                    "type": "integer",
                    "description": "ID de la VM",
                },
                "path": {
                    "type": "string",
                    "description": "Chemin du fichier dans la VM",
                },
            },
            "required": ["node", "vmid", "path"],
        },
    ),
    Tool(
        name="vm_file_write",
        description="Écrit un fichier dans une VM via le QEMU Guest Agent. "
        "Certains chemins système (/etc/shadow, /etc/passwd, etc.) sont protégés.",
        inputSchema={
            "type": "object",
            "properties": {
                "node": {
                    "type": "string",
                    "description": "Nom du nœud Proxmox",
                },
                "vmid": {
                    "type": "integer",
                    "description": "ID de la VM",
                },
                "path": {
                    "type": "string",
                    "description": "Chemin du fichier dans la VM",
                },
                "content": {
                    "type": "string",
                    "description": "Contenu à écrire",
                },
                "force": {
                    "type": "boolean",
                    "description": "Forcer l'écriture sur chemins protégés (défaut: false)",
                    "default": False,
                },
            },
            "required": ["node", "vmid", "path", "content"],
        },
    ),
    # Conteneurs LXC
    Tool(
        name="list_containers",
        description="Liste tous les conteneurs LXC du cluster ou d'un nœud spécifique",
        inputSchema={
            "type": "object",
            "properties": {
                "node": {
                    "type": "string",
                    "description": "Nom du nœud pour filtrer (optionnel)",
                }
            },
            "required": [],
        },
    ),
    Tool(
        name="get_container_details",
        description="Récupère la configuration complète d'un conteneur LXC: "
        "CPU, RAM, disques, réseau, statut",
        inputSchema={
            "type": "object",
            "properties": {
                "node": {
                    "type": "string",
                    "description": "Nom du nœud Proxmox",
                },
                "vmid": {
                    "type": "integer",
                    "description": "ID du conteneur",
                },
            },
            "required": ["node", "vmid"],
        },
    ),
    Tool(
        name="set_container_config",
        description="Modifie la configuration d'un conteneur LXC (CPU, RAM, swap, hostname, etc.)",
        inputSchema={
            "type": "object",
            "properties": {
                "node": {
                    "type": "string",
                    "description": "Nom du noeud Proxmox",
                },
                "vmid": {
                    "type": "integer",
                    "description": "ID du conteneur",
                },
                "cores": {
                    "type": "integer",
                    "description": "Nombre de coeurs CPU",
                },
                "memory": {
                    "type": "integer",
                    "description": "RAM en MB",
                },
                "swap": {
                    "type": "integer",
                    "description": "Swap en MB",
                },
                "hostname": {
                    "type": "string",
                    "description": "Nom d'hote du conteneur",
                },
                "description": {
                    "type": "string",
                    "description": "Description",
                },
                "onboot": {
                    "type": "boolean",
                    "description": "Demarrer au boot du noeud",
                },
                "cpulimit": {
                    "type": "number",
                    "description": "Limite CPU (0 = illimite)",
                },
                "cpuunits": {
                    "type": "integer",
                    "description": "Poids CPU relatif (1024 = defaut)",
                },
            },
            "required": ["node", "vmid"],
        },
    ),
    # Snapshots
    Tool(
        name="list_snapshots",
        description="Liste les snapshots d'une VM ou conteneur",
        inputSchema={
            "type": "object",
            "properties": {
                "node": {
                    "type": "string",
                    "description": "Nom du nœud Proxmox",
                },
                "vmid": {
                    "type": "integer",
                    "description": "ID de la VM/LXC",
                },
                "type": {
                    "type": "string",
                    "enum": ["qemu", "lxc"],
                    "description": "Type: qemu (VM) ou lxc (conteneur)",
                    "default": "qemu",
                },
            },
            "required": ["node", "vmid"],
        },
    ),
    Tool(
        name="create_snapshot",
        description="Crée un snapshot d'une VM ou conteneur",
        inputSchema={
            "type": "object",
            "properties": {
                "node": {
                    "type": "string",
                    "description": "Nom du nœud Proxmox",
                },
                "vmid": {
                    "type": "integer",
                    "description": "ID de la VM/LXC",
                },
                "type": {
                    "type": "string",
                    "enum": ["qemu", "lxc"],
                    "description": "Type: qemu (VM) ou lxc (conteneur)",
                },
                "name": {
                    "type": "string",
                    "description": "Nom du snapshot",
                },
                "description": {
                    "type": "string",
                    "description": "Description du snapshot (optionnel)",
                },
                "vmstate": {
                    "type": "boolean",
                    "description": "Inclure l'état RAM (VM QEMU uniquement)",
                    "default": False,
                },
            },
            "required": ["node", "vmid", "type", "name"],
        },
    ),
    Tool(
        name="delete_snapshot",
        description="Supprime un snapshot d'une VM ou conteneur",
        inputSchema={
            "type": "object",
            "properties": {
                "node": {
                    "type": "string",
                    "description": "Nom du nœud Proxmox",
                },
                "vmid": {
                    "type": "integer",
                    "description": "ID de la VM/LXC",
                },
                "type": {
                    "type": "string",
                    "enum": ["qemu", "lxc"],
                    "description": "Type: qemu (VM) ou lxc (conteneur)",
                },
                "snapname": {
                    "type": "string",
                    "description": "Nom du snapshot à supprimer",
                },
            },
            "required": ["node", "vmid", "type", "snapname"],
        },
    ),
    Tool(
        name="rollback_snapshot",
        description="Restaure une VM ou conteneur vers un snapshot. "
        "ATTENTION: L'état actuel non sauvegardé sera perdu!",
        inputSchema={
            "type": "object",
            "properties": {
                "node": {
                    "type": "string",
                    "description": "Nom du nœud Proxmox",
                },
                "vmid": {
                    "type": "integer",
                    "description": "ID de la VM/LXC",
                },
                "type": {
                    "type": "string",
                    "enum": ["qemu", "lxc"],
                    "description": "Type: qemu (VM) ou lxc (conteneur)",
                },
                "snapname": {
                    "type": "string",
                    "description": "Nom du snapshot à restaurer",
                },
            },
            "required": ["node", "vmid", "type", "snapname"],
        },
    ),
    # Stockage
    Tool(
        name="list_storage",
        description="Liste les pools de stockage d'un nœud avec utilisation",
        inputSchema={
            "type": "object",
            "properties": {
                "node": {
                    "type": "string",
                    "description": "Nom du nœud Proxmox",
                }
            },
            "required": ["node"],
        },
    ),
    Tool(
        name="get_storage_content",
        description="Liste le contenu d'un pool de stockage (images, ISOs, backups, etc.)",
        inputSchema={
            "type": "object",
            "properties": {
                "node": {
                    "type": "string",
                    "description": "Nom du nœud Proxmox",
                },
                "storage": {
                    "type": "string",
                    "description": "Nom du storage",
                },
                "content_type": {
                    "type": "string",
                    "description": "Filtrer par type (images, iso, vztmpl, backup)",
                },
            },
            "required": ["node", "storage"],
        },
    ),
    # Tâches
    Tool(
        name="list_tasks",
        description="Liste les tâches récentes d'un nœud Proxmox",
        inputSchema={
            "type": "object",
            "properties": {
                "node": {
                    "type": "string",
                    "description": "Nom du nœud Proxmox",
                },
                "limit": {
                    "type": "integer",
                    "description": "Nombre max de tâches (défaut: 50)",
                    "default": 50,
                },
                "vmid": {
                    "type": "integer",
                    "description": "Filtrer par ID de VM/LXC (optionnel)",
                },
            },
            "required": ["node"],
        },
    ),
    Tool(
        name="get_task_status",
        description="Récupère le statut détaillé d'une tâche Proxmox",
        inputSchema={
            "type": "object",
            "properties": {
                "node": {
                    "type": "string",
                    "description": "Nom du nœud Proxmox",
                },
                "upid": {
                    "type": "string",
                    "description": "ID unique de la tâche (UPID)",
                },
            },
            "required": ["node", "upid"],
        },
    ),
    # SSH
    Tool(
        name="ssh_execute",
        description="Exécute une commande SSH sur un nœud Proxmox. "
        "Permet d'administrer directement le système hôte.",
        inputSchema={
            "type": "object",
            "properties": {
                "node": {
                    "type": "string",
                    "description": "Nom du nœud Proxmox",
                },
                "command": {
                    "type": "string",
                    "description": "Commande shell à exécuter",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout en secondes (défaut: 30)",
                    "default": 30,
                },
            },
            "required": ["node", "command"],
        },
    ),
    Tool(
        name="ssh_read_file",
        description="Lit le contenu d'un fichier sur un nœud Proxmox via SSH",
        inputSchema={
            "type": "object",
            "properties": {
                "node": {
                    "type": "string",
                    "description": "Nom du nœud Proxmox",
                },
                "path": {
                    "type": "string",
                    "description": "Chemin absolu du fichier à lire",
                },
                "max_size": {
                    "type": "integer",
                    "description": "Taille max en bytes (défaut: 1MB)",
                    "default": 1048576,
                },
            },
            "required": ["node", "path"],
        },
    ),
    Tool(
        name="ssh_write_file",
        description="Écrit un fichier sur un nœud Proxmox via SSH. "
        "Crée automatiquement un backup du fichier existant.",
        inputSchema={
            "type": "object",
            "properties": {
                "node": {
                    "type": "string",
                    "description": "Nom du nœud Proxmox",
                },
                "path": {
                    "type": "string",
                    "description": "Chemin absolu du fichier",
                },
                "content": {
                    "type": "string",
                    "description": "Contenu à écrire",
                },
                "backup": {
                    "type": "boolean",
                    "description": "Créer un backup .bak (défaut: true)",
                    "default": True,
                },
                "mode": {
                    "type": "string",
                    "description": "Permissions du fichier (défaut: 0644)",
                    "default": "0644",
                },
            },
            "required": ["node", "path", "content"],
        },
    ),
    Tool(
        name="fix_apt_repos",
        description="Corrige les dépôts APT Proxmox pour les installations sans souscription. "
        "Désactive le dépôt enterprise et active le dépôt community no-subscription.",
        inputSchema={
            "type": "object",
            "properties": {
                "node": {
                    "type": "string",
                    "description": "Nom du nœud Proxmox",
                },
                "disable_enterprise": {
                    "type": "boolean",
                    "description": "Désactiver le dépôt enterprise (défaut: true)",
                    "default": True,
                },
                "enable_no_subscription": {
                    "type": "boolean",
                    "description": "Activer le dépôt no-subscription (défaut: true)",
                    "default": True,
                },
            },
            "required": ["node"],
        },
    ),
    # Users
    Tool(
        name="list_users",
        description="Liste tous les utilisateurs Proxmox",
        inputSchema={
            "type": "object",
            "properties": {},
            "required": [],
        },
    ),
    Tool(
        name="get_user",
        description="Récupère les détails d'un utilisateur Proxmox",
        inputSchema={
            "type": "object",
            "properties": {
                "userid": {
                    "type": "string",
                    "description": "ID de l'utilisateur (format: user@realm, ex: admin@pve)",
                },
            },
            "required": ["userid"],
        },
    ),
    Tool(
        name="create_user",
        description="Crée un nouvel utilisateur Proxmox",
        inputSchema={
            "type": "object",
            "properties": {
                "userid": {
                    "type": "string",
                    "description": "ID de l'utilisateur (format: user@realm, ex: admin@pve ou user@pam)",
                },
                "password": {
                    "type": "string",
                    "description": "Mot de passe (requis pour realm pve)",
                },
                "email": {
                    "type": "string",
                    "description": "Adresse email",
                },
                "firstname": {
                    "type": "string",
                    "description": "Prénom",
                },
                "lastname": {
                    "type": "string",
                    "description": "Nom",
                },
                "comment": {
                    "type": "string",
                    "description": "Commentaire/description",
                },
                "groups": {
                    "type": "string",
                    "description": "Groupes (séparés par des virgules)",
                },
                "expire": {
                    "type": "integer",
                    "description": "Timestamp d'expiration (0 = jamais, defaut: 0)",
                    "default": 0,
                },
                "enable": {
                    "type": "boolean",
                    "description": "Activer l'utilisateur (défaut: true)",
                    "default": True,
                },
            },
            "required": ["userid"],
        },
    ),
    Tool(
        name="update_user",
        description="Modifie un utilisateur Proxmox existant",
        inputSchema={
            "type": "object",
            "properties": {
                "userid": {
                    "type": "string",
                    "description": "ID de l'utilisateur (format: user@realm)",
                },
                "password": {
                    "type": "string",
                    "description": "Nouveau mot de passe",
                },
                "email": {
                    "type": "string",
                    "description": "Nouvelle adresse email",
                },
                "firstname": {
                    "type": "string",
                    "description": "Nouveau prénom",
                },
                "lastname": {
                    "type": "string",
                    "description": "Nouveau nom",
                },
                "comment": {
                    "type": "string",
                    "description": "Nouveau commentaire",
                },
                "groups": {
                    "type": "string",
                    "description": "Nouveaux groupes (séparés par des virgules)",
                },
                "enable": {
                    "type": "boolean",
                    "description": "Activer/désactiver l'utilisateur",
                },
            },
            "required": ["userid"],
        },
    ),
    Tool(
        name="delete_user",
        description="Supprime un utilisateur Proxmox. ATTENTION: Action irréversible!",
        inputSchema={
            "type": "object",
            "properties": {
                "userid": {
                    "type": "string",
                    "description": "ID de l'utilisateur à supprimer (format: user@realm)",
                },
            },
            "required": ["userid"],
        },
    ),
]


@server.list_tools()
async def list_tools() -> list[Tool]:
    """Retourne la liste des tools disponibles."""
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Exécute un tool et retourne le résultat.

    Args:
        name: Nom du tool à exécuter
        arguments: Arguments du tool

    Returns:
        Résultat formaté en JSON
    """
    client = _get_client()
    result: dict[str, Any]

    try:
        match name:
            # Nœuds
            case "list_nodes":
                result = await nodes.list_nodes(client)
            case "get_node_status":
                result = await nodes.get_node_status(client, arguments["node"])

            # VMs
            case "list_vms":
                result = await vms.list_vms(client, arguments.get("node"))
            case "get_vm_details":
                result = await vms.get_vm_details(client, arguments["node"], arguments["vmid"])
            case "start_vm":
                result = await vms.start_vm(
                    client,
                    arguments["node"],
                    arguments["vmid"],
                    arguments.get("type", "qemu"),
                )
            case "stop_vm":
                result = await vms.stop_vm(
                    client,
                    arguments["node"],
                    arguments["vmid"],
                    arguments.get("type", "qemu"),
                )
            case "shutdown_vm":
                result = await vms.shutdown_vm(
                    client,
                    arguments["node"],
                    arguments["vmid"],
                    arguments.get("type", "qemu"),
                )
            case "reboot_vm":
                result = await vms.reboot_vm(
                    client,
                    arguments["node"],
                    arguments["vmid"],
                    arguments.get("type", "qemu"),
                )
            case "destroy_vm":
                result = await vms.destroy_vm(
                    client,
                    arguments["node"],
                    arguments["vmid"],
                    arguments.get("type", "qemu"),
                    arguments.get("purge", True),
                )
            case "set_vm_config":
                result = await vms.set_vm_config(
                    client,
                    arguments["node"],
                    arguments["vmid"],
                    cores=arguments.get("cores"),
                    sockets=arguments.get("sockets"),
                    memory=arguments.get("memory"),
                    balloon=arguments.get("balloon"),
                    name=arguments.get("name"),
                    description=arguments.get("description"),
                    onboot=arguments.get("onboot"),
                    cpulimit=arguments.get("cpulimit"),
                    cpuunits=arguments.get("cpuunits"),
                )

            # Guest Agent
            case "vm_exec":
                result = await vms.vm_exec(
                    client,
                    arguments["node"],
                    arguments["vmid"],
                    arguments["command"],
                )
            case "vm_exec_status":
                result = await vms.vm_exec_status(
                    client,
                    arguments["node"],
                    arguments["vmid"],
                    arguments["pid"],
                )
            case "vm_exec_sync":
                result = await vms.vm_exec_sync(
                    _get_ssh_client(),
                    arguments["node"],
                    arguments["vmid"],
                    arguments["command"],
                    arguments.get("timeout", 30),
                )
            case "vm_file_read":
                result = await vms.vm_file_read(
                    client,
                    arguments["node"],
                    arguments["vmid"],
                    arguments["path"],
                )
            case "vm_file_write":
                result = await vms.vm_file_write(
                    client,
                    arguments["node"],
                    arguments["vmid"],
                    arguments["path"],
                    arguments["content"],
                    arguments.get("force", False),
                )

            # Conteneurs
            case "list_containers":
                result = await containers.list_containers(client, arguments.get("node"))
            case "get_container_details":
                result = await containers.get_container_details(
                    client, arguments["node"], arguments["vmid"]
                )
            case "set_container_config":
                result = await containers.set_container_config(
                    client,
                    arguments["node"],
                    arguments["vmid"],
                    cores=arguments.get("cores"),
                    memory=arguments.get("memory"),
                    swap=arguments.get("swap"),
                    hostname=arguments.get("hostname"),
                    description=arguments.get("description"),
                    onboot=arguments.get("onboot"),
                    cpulimit=arguments.get("cpulimit"),
                    cpuunits=arguments.get("cpuunits"),
                )

            # Snapshots
            case "list_snapshots":
                result = await snapshots.list_snapshots(
                    client,
                    arguments["node"],
                    arguments["vmid"],
                    arguments.get("type", "qemu"),
                )
            case "create_snapshot":
                result = await snapshots.create_snapshot(
                    client,
                    arguments["node"],
                    arguments["vmid"],
                    arguments["type"],
                    arguments["name"],
                    arguments.get("description"),
                    arguments.get("vmstate", False),
                )
            case "delete_snapshot":
                result = await snapshots.delete_snapshot(
                    client,
                    arguments["node"],
                    arguments["vmid"],
                    arguments["type"],
                    arguments["snapname"],
                )
            case "rollback_snapshot":
                result = await snapshots.rollback_snapshot(
                    client,
                    arguments["node"],
                    arguments["vmid"],
                    arguments["type"],
                    arguments["snapname"],
                )

            # Stockage
            case "list_storage":
                result = await storage.list_storage(client, arguments["node"])
            case "get_storage_content":
                result = await storage.get_storage_content(
                    client,
                    arguments["node"],
                    arguments["storage"],
                    arguments.get("content_type"),
                )

            # Tâches
            case "list_tasks":
                result = await tasks.list_tasks(
                    client,
                    arguments["node"],
                    arguments.get("limit", 50),
                    arguments.get("vmid"),
                )
            case "get_task_status":
                result = await tasks.get_task_status(client, arguments["node"], arguments["upid"])

            # SSH
            case "ssh_execute":
                result = await ssh.ssh_execute(
                    _get_ssh_client(),
                    arguments["node"],
                    arguments["command"],
                    arguments.get("timeout", 30),
                )
            case "ssh_read_file":
                result = await ssh.ssh_read_file(
                    _get_ssh_client(),
                    arguments["node"],
                    arguments["path"],
                    arguments.get("max_size", 1048576),
                )
            case "ssh_write_file":
                result = await ssh.ssh_write_file(
                    _get_ssh_client(),
                    arguments["node"],
                    arguments["path"],
                    arguments["content"],
                    arguments.get("backup", True),
                    arguments.get("mode", "0644"),
                )
            case "fix_apt_repos":
                result = await ssh.fix_apt_repos(
                    _get_ssh_client(),
                    arguments["node"],
                    arguments.get("disable_enterprise", True),
                    arguments.get("enable_no_subscription", True),
                )

            # Users
            case "list_users":
                result = await users.list_users(client)
            case "get_user":
                result = await users.get_user(client, arguments["userid"])
            case "create_user":
                result = await users.create_user(
                    client,
                    arguments["userid"],
                    arguments.get("password"),
                    arguments.get("email"),
                    arguments.get("firstname"),
                    arguments.get("lastname"),
                    arguments.get("comment"),
                    arguments.get("groups"),
                    arguments.get("expire", 0),
                    arguments.get("enable", True),
                )
            case "update_user":
                result = await users.update_user(
                    client,
                    arguments["userid"],
                    arguments.get("password"),
                    arguments.get("email"),
                    arguments.get("firstname"),
                    arguments.get("lastname"),
                    arguments.get("comment"),
                    arguments.get("groups"),
                    arguments.get("expire"),
                    arguments.get("enable"),
                )
            case "delete_user":
                result = await users.delete_user(client, arguments["userid"])

            case _:
                result = {
                    "success": False,
                    "error": f"Tool inconnu: {name}",
                    "error_code": "UNKNOWN_TOOL",
                }

    except Exception as e:
        logger.exception(f"Erreur lors de l'exécution du tool {name}")
        result = {
            "success": False,
            "error": str(e),
            "error_code": "INTERNAL_ERROR",
        }

    return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]


async def run_server() -> None:
    """Lance le serveur MCP."""
    global _client, _ssh_client

    logger.info("Démarrage du serveur MCP Proxmox...")

    # Charger la configuration
    try:
        config = get_config()
        logger.info(f"Configuration chargée: {config.host}:{config.port}")
    except Exception as e:
        logger.error(f"Erreur de configuration: {e}")
        sys.exit(1)

    # Initialiser le client Proxmox
    _client = ProxmoxClient(config)
    set_client(_client)

    # Initialiser le client SSH si configuré
    if config.ssh.enabled:
        _ssh_client = SSHClient(config, config.ssh)
        set_ssh_client(_ssh_client)
        logger.info("Client SSH initialisé")
    else:
        logger.info("SSH désactivé (PROXMOX_SSH_KEY_PATH ou PROXMOX_SSH_PASSWORD non configuré)")

    async with _client:
        logger.info("Client Proxmox connecté")

        # Entrer dans le context manager SSH si activé
        if _ssh_client:
            async with _ssh_client:
                async with stdio_server() as (read_stream, write_stream):
                    logger.info("Serveur MCP prêt (avec SSH)")
                    await server.run(
                        read_stream,
                        write_stream,
                        server.create_initialization_options(),
                    )
        else:
            # Lancer le serveur MCP via stdio sans SSH
            async with stdio_server() as (read_stream, write_stream):
                logger.info("Serveur MCP prêt (sans SSH)")
                await server.run(
                    read_stream,
                    write_stream,
                    server.create_initialization_options(),
                )


def main() -> None:
    """Point d'entrée principal."""
    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        logger.info("Arrêt du serveur...")
    except Exception as e:
        logger.exception(f"Erreur fatale: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
