"""Configuration pour le serveur MCP Proxmox."""

import os
from functools import lru_cache

from dotenv import load_dotenv
from typing import Literal

from pydantic import BaseModel, field_validator, model_validator


class SSHConfig(BaseModel):
    """Configuration SSH pour l'accès direct aux nœuds Proxmox.

    Attributes:
        enabled: Active/désactive les fonctionnalités SSH
        user: Utilisateur SSH (défaut: root)
        key_path: Chemin vers la clé privée SSH
        password: Mot de passe SSH (fallback si pas de clé)
        port: Port SSH (défaut: 22)
        timeout: Timeout de connexion en secondes
    """

    enabled: bool = False
    user: str = "root"
    key_path: str | None = None
    password: str | None = None
    port: int = 22
    timeout: int = 30

    @model_validator(mode="after")
    def validate_ssh_auth(self) -> "SSHConfig":
        """Valide qu'au moins une méthode d'auth SSH est configurée si enabled."""
        if self.enabled and not self.key_path and not self.password:
            raise ValueError(
                "SSH activé mais aucune méthode d'authentification: "
                "PROXMOX_SSH_KEY_PATH ou PROXMOX_SSH_PASSWORD requis"
            )
        return self

    @property
    def has_auth(self) -> bool:
        """Indique si une méthode d'authentification SSH est configurée."""
        return self.key_path is not None or self.password is not None


class ProxmoxConfig(BaseModel):
    """Configuration de connexion à l'API Proxmox.

    Attributes:
        host: Adresse IP ou hostname du serveur Proxmox (sans https://, sans port)
        port: Port de l'API Proxmox (défaut: 8006)
        verify_ssl: Vérification du certificat SSL (défaut: False pour self-signed)
        timeout: Timeout des requêtes en secondes (défaut: 30)
        token_id: ID du token API (format: user@pam!token-name)
        token_secret: Secret du token API (format UUID)
        user: Utilisateur Proxmox (format: user@pam)
        password: Mot de passe de l'utilisateur
    """

    host: str
    port: int = 8006
    verify_ssl: bool = False
    timeout: int = 30
    # Auth token
    token_id: str | None = None
    token_secret: str | None = None
    # Auth password
    user: str | None = None
    password: str | None = None
    # SSH config
    ssh: SSHConfig = SSHConfig()
    # Mapping node name -> IP for multi-node SSH
    node_ips: dict[str, str] = {}

    @field_validator("host")
    @classmethod
    def validate_host(cls, v: str) -> str:
        """Valide et nettoie le host."""
        # Retirer https:// ou http:// si présent
        if v.startswith("https://"):
            v = v[8:]
        elif v.startswith("http://"):
            v = v[7:]
        # Retirer le port si présent
        if ":" in v:
            v = v.split(":")[0]
        # Retirer le slash final si présent
        return v.rstrip("/")

    @model_validator(mode="after")
    def validate_auth(self) -> "ProxmoxConfig":
        """Valide qu'au moins une méthode d'authentification est configurée."""
        has_token = self.token_id is not None and self.token_secret is not None
        has_password = self.user is not None and self.password is not None

        if not has_token and not has_password:
            raise ValueError(
                "Au moins une méthode d'authentification requise: "
                "token (PROXMOX_TOKEN_ID + PROXMOX_TOKEN_SECRET) ou "
                "password (PROXMOX_USER + PROXMOX_PASSWORD)"
            )
        return self

    @property
    def use_token_auth(self) -> bool:
        """Indique si l'authentification par token est utilisée."""
        return self.token_id is not None and self.token_secret is not None

    @property
    def base_url(self) -> str:
        """URL de base de l'API Proxmox."""
        return f"https://{self.host}:{self.port}/api2/json"


@lru_cache
def get_config() -> ProxmoxConfig:
    """Charge la configuration depuis les variables d'environnement.

    Returns:
        Configuration Proxmox validée

    Raises:
        ValueError: Si la configuration est invalide
    """
    load_dotenv()

    # Charger la configuration SSH
    ssh_key_path = os.environ.get("PROXMOX_SSH_KEY_PATH")
    ssh_password = os.environ.get("PROXMOX_SSH_PASSWORD")
    # SSH est activé automatiquement si une méthode d'auth est configurée
    ssh_enabled = ssh_key_path is not None or ssh_password is not None

    ssh_config = SSHConfig(
        enabled=ssh_enabled,
        user=os.environ.get("PROXMOX_SSH_USER", "root"),
        key_path=ssh_key_path,
        password=ssh_password,
        port=int(os.environ.get("PROXMOX_SSH_PORT", "22")),
        timeout=int(os.environ.get("PROXMOX_SSH_TIMEOUT", "30")),
    )

    # Parse node IPs mapping (format: "node1:ip1,node2:ip2")
    node_ips: dict[str, str] = {}
    node_ips_str = os.environ.get("PROXMOX_NODE_IPS", "")
    if node_ips_str:
        for pair in node_ips_str.split(","):
            if ":" in pair:
                name, ip = pair.split(":", 1)
                node_ips[name.strip()] = ip.strip()

    return ProxmoxConfig(
        host=os.environ.get("PROXMOX_HOST", ""),
        port=int(os.environ.get("PROXMOX_PORT", "8006")),
        verify_ssl=os.environ.get("PROXMOX_VERIFY_SSL", "false").lower() == "true",
        timeout=int(os.environ.get("PROXMOX_TIMEOUT", "30")),
        token_id=os.environ.get("PROXMOX_TOKEN_ID"),
        token_secret=os.environ.get("PROXMOX_TOKEN_SECRET"),
        user=os.environ.get("PROXMOX_USER"),
        password=os.environ.get("PROXMOX_PASSWORD"),
        ssh=ssh_config,
        node_ips=node_ips,
    )
