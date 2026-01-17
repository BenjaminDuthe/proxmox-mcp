"""Modèles Pydantic pour les entrées/sorties de l'API Proxmox."""

from typing import Any, Literal

from pydantic import BaseModel, Field


# =============================================================================
# Types communs
# =============================================================================

VMType = Literal["qemu", "lxc"]


# =============================================================================
# Modèles de réponse - Nœuds
# =============================================================================


class NodeInfo(BaseModel):
    """Informations sur un nœud Proxmox."""

    node: str = Field(description="Nom du nœud")
    status: str = Field(description="Statut du nœud (online, offline)")
    cpu: float = Field(default=0, description="Utilisation CPU (0-1)")
    maxcpu: int = Field(default=0, description="Nombre de CPUs")
    mem: int = Field(default=0, description="Mémoire utilisée en bytes")
    maxmem: int = Field(default=0, description="Mémoire totale en bytes")
    disk: int = Field(default=0, description="Espace disque utilisé en bytes")
    maxdisk: int = Field(default=0, description="Espace disque total en bytes")
    uptime: int = Field(default=0, description="Uptime en secondes")

    @property
    def cpu_percent(self) -> float:
        """Utilisation CPU en pourcentage."""
        return round(self.cpu * 100, 2)

    @property
    def mem_percent(self) -> float:
        """Utilisation mémoire en pourcentage."""
        if self.maxmem == 0:
            return 0
        return round((self.mem / self.maxmem) * 100, 2)

    @property
    def disk_percent(self) -> float:
        """Utilisation disque en pourcentage."""
        if self.maxdisk == 0:
            return 0
        return round((self.disk / self.maxdisk) * 100, 2)


# =============================================================================
# Modèles de réponse - VMs et Conteneurs
# =============================================================================


class VMInfo(BaseModel):
    """Informations sur une VM QEMU ou un conteneur LXC."""

    vmid: int = Field(description="ID de la VM/LXC")
    name: str = Field(default="", description="Nom de la VM/LXC")
    status: str = Field(description="Statut (running, stopped, paused)")
    node: str = Field(description="Nœud hébergeant la VM/LXC")
    type: VMType = Field(description="Type: qemu ou lxc")
    cpu: float = Field(default=0, description="Utilisation CPU (0-1)")
    cpus: int = Field(default=1, description="Nombre de vCPUs alloués")
    mem: int = Field(default=0, description="Mémoire utilisée en bytes")
    maxmem: int = Field(default=0, description="Mémoire allouée en bytes")
    disk: int = Field(default=0, description="Espace disque utilisé en bytes")
    maxdisk: int = Field(default=0, description="Espace disque alloué en bytes")
    uptime: int = Field(default=0, description="Uptime en secondes")
    netin: int = Field(default=0, description="Trafic réseau entrant en bytes")
    netout: int = Field(default=0, description="Trafic réseau sortant en bytes")

    @property
    def cpu_percent(self) -> float:
        """Utilisation CPU en pourcentage."""
        return round(self.cpu * 100, 2)

    @property
    def mem_percent(self) -> float:
        """Utilisation mémoire en pourcentage."""
        if self.maxmem == 0:
            return 0
        return round((self.mem / self.maxmem) * 100, 2)


class VMConfig(BaseModel):
    """Configuration détaillée d'une VM ou conteneur."""

    vmid: int
    name: str = ""
    description: str = ""
    cores: int = 1
    memory: int = 512  # MB
    balloon: int | None = None  # MB, si balloon activé
    ostype: str = ""
    boot: str = ""
    # Réseau et disques sont dynamiques, on les garde en dict
    networks: dict[str, Any] = Field(default_factory=dict)
    disks: dict[str, Any] = Field(default_factory=dict)
    # Config brute complète
    raw_config: dict[str, Any] = Field(default_factory=dict)


# =============================================================================
# Modèles de réponse - Snapshots
# =============================================================================


class SnapshotInfo(BaseModel):
    """Informations sur un snapshot."""

    name: str = Field(description="Nom du snapshot")
    description: str | None = Field(default=None, description="Description du snapshot")
    snaptime: int | None = Field(default=None, description="Timestamp de création")
    parent: str | None = Field(default=None, description="Snapshot parent")
    vmstate: bool = Field(default=False, description="Inclut l'état RAM")


# =============================================================================
# Modèles de réponse - Stockage
# =============================================================================


class StorageInfo(BaseModel):
    """Informations sur un pool de stockage."""

    storage: str = Field(description="Nom du storage")
    type: str = Field(description="Type de storage (dir, lvm, zfs, etc.)")
    content: str = Field(default="", description="Types de contenu supportés")
    active: bool = Field(default=True, description="Storage actif")
    enabled: bool = Field(default=True, description="Storage activé")
    shared: bool = Field(default=False, description="Storage partagé")
    used: int = Field(default=0, description="Espace utilisé en bytes")
    avail: int = Field(default=0, description="Espace disponible en bytes")
    total: int = Field(default=0, description="Espace total en bytes")

    @property
    def used_percent(self) -> float:
        """Utilisation en pourcentage."""
        if self.total == 0:
            return 0
        return round((self.used / self.total) * 100, 2)


class StorageContent(BaseModel):
    """Élément de contenu dans un storage."""

    volid: str = Field(description="ID du volume")
    format: str = Field(default="", description="Format (qcow2, raw, etc.)")
    size: int = Field(default=0, description="Taille en bytes")
    ctime: int | None = Field(default=None, description="Timestamp de création")
    vmid: int | None = Field(default=None, description="VMID associé si applicable")
    content: str = Field(default="", description="Type de contenu")


# =============================================================================
# Modèles de réponse - Tâches
# =============================================================================


class TaskInfo(BaseModel):
    """Informations sur une tâche Proxmox."""

    upid: str = Field(description="ID unique de la tâche (UPID)")
    node: str = Field(description="Nœud exécutant la tâche")
    type: str = Field(description="Type de tâche (qmstart, qmstop, etc.)")
    status: str = Field(default="", description="Statut de la tâche")
    user: str = Field(default="", description="Utilisateur ayant lancé la tâche")
    starttime: int = Field(default=0, description="Timestamp de démarrage")
    endtime: int | None = Field(default=None, description="Timestamp de fin")
    exitstatus: str | None = Field(default=None, description="Statut de sortie")
    id: str = Field(default="", description="ID de la ressource concernée")


class TaskStatus(BaseModel):
    """Statut détaillé d'une tâche."""

    upid: str
    node: str
    type: str
    status: str  # running, stopped
    exitstatus: str | None = None
    user: str = ""
    starttime: int = 0
    pid: int | None = None
    pstart: int | None = None


# =============================================================================
# Modèles d'entrée - Paramètres des tools
# =============================================================================


class VMActionParams(BaseModel):
    """Paramètres pour une action sur VM/LXC."""

    node: str = Field(description="Nom du nœud Proxmox")
    vmid: int = Field(description="ID de la VM/LXC")
    type: VMType = Field(description="Type: qemu ou lxc")


class SnapshotCreateParams(BaseModel):
    """Paramètres pour créer un snapshot."""

    node: str = Field(description="Nom du nœud Proxmox")
    vmid: int = Field(description="ID de la VM/LXC")
    type: VMType = Field(description="Type: qemu ou lxc")
    name: str = Field(description="Nom du snapshot")
    description: str | None = Field(default=None, description="Description optionnelle")
    vmstate: bool = Field(default=False, description="Inclure l'état RAM (VM uniquement)")


class SnapshotActionParams(BaseModel):
    """Paramètres pour une action sur snapshot."""

    node: str = Field(description="Nom du nœud Proxmox")
    vmid: int = Field(description="ID de la VM/LXC")
    type: VMType = Field(description="Type: qemu ou lxc")
    snapname: str = Field(description="Nom du snapshot")


class DestroyVMParams(BaseModel):
    """Paramètres pour supprimer une VM/LXC."""

    node: str = Field(description="Nom du nœud Proxmox")
    vmid: int = Field(description="ID de la VM/LXC")
    type: VMType = Field(description="Type: qemu ou lxc")
    purge: bool = Field(default=True, description="Purger les jobs et configs liés")
    destroy_unreferenced_disks: bool = Field(
        default=True, description="Supprimer les disques non référencés"
    )


# =============================================================================
# Modèles de réponse - SSH
# =============================================================================


class SSHCommandResult(BaseModel):
    """Résultat d'une commande SSH."""

    command: str = Field(description="Commande exécutée")
    exit_code: int = Field(description="Code de retour")
    stdout: str = Field(default="", description="Sortie standard")
    stderr: str = Field(default="", description="Sortie d'erreur")
    duration_ms: int = Field(default=0, description="Durée d'exécution en ms")


class SSHFileInfo(BaseModel):
    """Informations sur un fichier distant."""

    path: str = Field(description="Chemin du fichier")
    exists: bool = Field(description="Le fichier existe")
    size: int | None = Field(default=None, description="Taille en bytes")
    content: str | None = Field(default=None, description="Contenu du fichier")
    backup_path: str | None = Field(default=None, description="Chemin du backup si créé")
