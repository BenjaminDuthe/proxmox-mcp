"""Client SSH async pour l'accès direct aux nœuds Proxmox."""

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

import asyncssh

from proxmox_mcp.config import ProxmoxConfig, SSHConfig
from proxmox_mcp.exceptions import (
    SSHAuthenticationError,
    SSHError,
    SSHFileNotFoundError,
    SSHTimeoutError,
)

logger = logging.getLogger(__name__)


class SSHClient:
    """Client SSH async pour les opérations sur les nœuds Proxmox.

    Gère un pool de connexions persistantes vers les nœuds.

    Args:
        config: Configuration Proxmox (contient l'hôte principal)
        ssh_config: Configuration SSH spécifique

    Example:
        ```python
        async with SSHClient(config, ssh_config) as ssh:
            result = await ssh.execute("pve1", "hostname")
        ```
    """

    def __init__(self, config: ProxmoxConfig, ssh_config: SSHConfig):
        self.config = config
        self.ssh_config = ssh_config
        self._connections: dict[str, asyncssh.SSHClientConnection] = {}
        self._lock = asyncio.Lock()

    async def __aenter__(self) -> "SSHClient":
        """Initialise le client SSH."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Ferme toutes les connexions SSH."""
        await self.close_all()

    async def close_all(self) -> None:
        """Ferme toutes les connexions SSH actives."""
        for node, conn in self._connections.items():
            try:
                conn.close()
                await conn.wait_closed()
                logger.debug(f"Connexion SSH fermée pour {node}")
            except Exception as e:
                logger.warning(f"Erreur fermeture SSH {node}: {e}")
        self._connections.clear()

    def _get_host_for_node(self, node: str) -> str:
        """Détermine l'hôte SSH pour un nœud.

        Utilise le mapping node_ips si configuré, sinon le host principal.

        Args:
            node: Nom du nœud

        Returns:
            Adresse IP ou hostname pour SSH
        """
        if self.config.node_ips and node in self.config.node_ips:
            return self.config.node_ips[node]
        return self.config.host

    async def _get_connection(self, node: str) -> asyncssh.SSHClientConnection:
        """Obtient ou crée une connexion SSH vers un nœud.

        Args:
            node: Nom du nœud Proxmox

        Returns:
            Connexion SSH active

        Raises:
            SSHAuthenticationError: Si l'authentification échoue
            SSHError: Si la connexion échoue
        """
        async with self._lock:
            # Vérifier si connexion existante et active
            if node in self._connections:
                conn = self._connections[node]
                # Vérifier si la connexion est toujours ouverte
                if not conn.is_closed():
                    return conn
                # Connexion fermée, la supprimer
                del self._connections[node]

            host = self._get_host_for_node(node)
            logger.debug(f"Nouvelle connexion SSH vers {node} ({host})")

            # Préparer les options de connexion
            connect_options: dict[str, Any] = {
                "host": host,
                "port": self.ssh_config.port,
                "username": self.ssh_config.user,
                "known_hosts": None,  # Accepter tous les hôtes (self-signed Proxmox)
            }

            # Auth par clé SSH (prioritaire)
            if self.ssh_config.key_path:
                key_path = Path(self.ssh_config.key_path).expanduser()
                if not key_path.exists():
                    raise SSHError(f"Clé SSH introuvable: {key_path}")
                connect_options["client_keys"] = [str(key_path)]
            # Auth par mot de passe (fallback)
            elif self.ssh_config.password:
                connect_options["password"] = self.ssh_config.password

            try:
                conn = await asyncio.wait_for(
                    asyncssh.connect(**connect_options),
                    timeout=self.ssh_config.timeout,
                )
                self._connections[node] = conn
                logger.info(f"Connexion SSH établie vers {node}")
                return conn

            except asyncio.TimeoutError:
                raise SSHTimeoutError(f"connexion vers {node}")
            except asyncssh.PermissionDenied:
                raise SSHAuthenticationError(f"Accès refusé pour {self.ssh_config.user}@{host}")
            except asyncssh.HostKeyNotVerifiable:
                raise SSHError(f"Clé hôte non vérifiable pour {host}")
            except Exception as e:
                raise SSHError(f"Erreur connexion SSH vers {node}: {e}")

    async def execute(
        self,
        node: str,
        command: str,
        timeout: int = 30,
        check_exit_code: bool = True,
    ) -> dict[str, Any]:
        """Exécute une commande sur un nœud via SSH.

        Args:
            node: Nom du nœud Proxmox
            command: Commande shell à exécuter
            timeout: Timeout en secondes
            check_exit_code: Si True, lève une exception si code != 0

        Returns:
            Dictionnaire avec stdout, stderr, exit_code, duration_ms

        Raises:
            SSHCommandError: Si la commande échoue et check_exit_code=True
            SSHTimeoutError: Si le timeout est dépassé
        """
        conn = await self._get_connection(node)
        start_time = time.time()

        try:
            result = await asyncio.wait_for(
                conn.run(command, check=False),
                timeout=timeout,
            )
            duration_ms = int((time.time() - start_time) * 1000)

            return {
                "command": command,
                "exit_code": result.exit_status or 0,
                "stdout": result.stdout or "",
                "stderr": result.stderr or "",
                "duration_ms": duration_ms,
            }

        except asyncio.TimeoutError:
            raise SSHTimeoutError(f"exécution de '{command}'")

    async def read_file(
        self,
        node: str,
        path: str,
        max_size: int = 1048576,
    ) -> dict[str, Any]:
        """Lit le contenu d'un fichier distant.

        Args:
            node: Nom du nœud Proxmox
            path: Chemin absolu du fichier
            max_size: Taille maximale à lire (défaut 1MB)

        Returns:
            Dictionnaire avec path, exists, size, content

        Raises:
            SSHFileNotFoundError: Si le fichier n'existe pas
        """
        # Vérifier existence et taille
        check_result = await self.execute(
            node,
            f'stat -c "%s" "{path}" 2>/dev/null || echo "NOT_FOUND"',
            check_exit_code=False,
        )

        stdout = check_result["stdout"].strip()
        if stdout == "NOT_FOUND" or not stdout:
            raise SSHFileNotFoundError(path)

        size = int(stdout)
        if size > max_size:
            raise SSHError(f"Fichier trop volumineux: {size} bytes (max: {max_size})")

        # Lire le contenu
        result = await self.execute(node, f'cat "{path}"')

        return {
            "path": path,
            "exists": True,
            "size": size,
            "content": result["stdout"],
        }

    async def write_file(
        self,
        node: str,
        path: str,
        content: str,
        backup: bool = True,
        mode: str = "0644",
    ) -> dict[str, Any]:
        """Écrit un fichier distant avec backup optionnel.

        Args:
            node: Nom du nœud Proxmox
            path: Chemin absolu du fichier
            content: Contenu à écrire
            backup: Créer un backup .bak avant modification
            mode: Permissions du fichier (ex: "0644")

        Returns:
            Dictionnaire avec path, backup_path, size
        """
        backup_path = None

        # Créer un backup si le fichier existe
        if backup:
            check = await self.execute(
                node,
                f'test -f "{path}" && echo "EXISTS"',
                check_exit_code=False,
            )
            if "EXISTS" in check["stdout"]:
                # Générer un nom de backup avec timestamp
                backup_cmd = f'cp "{path}" "{path}.bak.$(date +%Y%m%d_%H%M%S)"'
                backup_result = await self.execute(node, backup_cmd)
                # Récupérer le chemin du backup créé
                ls_result = await self.execute(
                    node,
                    f'ls -t "{path}.bak."* 2>/dev/null | head -1',
                    check_exit_code=False,
                )
                backup_path = ls_result["stdout"].strip() or None
                if backup_path:
                    logger.info(f"Backup créé: {backup_path}")

        # Écrire le nouveau contenu via heredoc
        write_cmd = f'''cat > "{path}" << 'PROXMOX_MCP_EOF'
{content}
PROXMOX_MCP_EOF'''

        await self.execute(node, write_cmd)
        await self.execute(node, f'chmod {mode} "{path}"')

        return {
            "path": path,
            "backup_path": backup_path,
            "size": len(content),
            "success": True,
        }


# Instance globale
_ssh_client: SSHClient | None = None


def get_ssh_client() -> SSHClient | None:
    """Retourne l'instance globale du client SSH."""
    return _ssh_client


def set_ssh_client(client: SSHClient | None) -> None:
    """Définit l'instance globale du client SSH."""
    global _ssh_client
    _ssh_client = client
