"""Exceptions personnalisées pour le client Proxmox MCP."""

from enum import Enum


class ErrorCode(str, Enum):
    """Codes d'erreur standardisés pour les réponses API."""

    AUTH_FAILED = "AUTH_FAILED"
    CONNECTION_ERROR = "CONNECTION_ERROR"
    NODE_NOT_FOUND = "NODE_NOT_FOUND"
    VM_NOT_FOUND = "VM_NOT_FOUND"
    SNAPSHOT_NOT_FOUND = "SNAPSHOT_NOT_FOUND"
    STORAGE_NOT_FOUND = "STORAGE_NOT_FOUND"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    TASK_FAILED = "TASK_FAILED"
    INVALID_STATE = "INVALID_STATE"
    API_ERROR = "API_ERROR"
    # Users
    USER_NOT_FOUND = "USER_NOT_FOUND"
    INVALID_FORMAT = "INVALID_FORMAT"
    PASSWORD_REQUIRED = "PASSWORD_REQUIRED"
    NO_CHANGES = "NO_CHANGES"
    # SSH
    SSH_AUTH_FAILED = "SSH_AUTH_FAILED"
    SSH_CONNECTION_ERROR = "SSH_CONNECTION_ERROR"
    SSH_COMMAND_FAILED = "SSH_COMMAND_FAILED"
    SSH_FILE_NOT_FOUND = "SSH_FILE_NOT_FOUND"
    SSH_TIMEOUT = "SSH_TIMEOUT"


class ProxmoxError(Exception):
    """Exception de base pour les erreurs Proxmox."""

    def __init__(self, message: str, error_code: ErrorCode = ErrorCode.API_ERROR):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)

    def to_dict(self) -> dict:
        """Convertit l'exception en dictionnaire de réponse."""
        return {
            "success": False,
            "error": self.message,
            "error_code": self.error_code.value,
        }


class AuthenticationError(ProxmoxError):
    """Erreur d'authentification auprès de l'API Proxmox."""

    def __init__(self, message: str = "Échec de l'authentification"):
        super().__init__(message, ErrorCode.AUTH_FAILED)


class ConnectionError(ProxmoxError):
    """Erreur de connexion au serveur Proxmox."""

    def __init__(self, message: str = "Impossible de se connecter au serveur Proxmox"):
        super().__init__(message, ErrorCode.CONNECTION_ERROR)


class NodeNotFoundError(ProxmoxError):
    """Nœud Proxmox introuvable."""

    def __init__(self, node: str):
        super().__init__(f"Nœud '{node}' introuvable", ErrorCode.NODE_NOT_FOUND)


class VMNotFoundError(ProxmoxError):
    """VM ou conteneur LXC introuvable."""

    def __init__(self, vmid: int, node: str | None = None):
        location = f" sur le nœud '{node}'" if node else ""
        super().__init__(f"VM/LXC {vmid} introuvable{location}", ErrorCode.VM_NOT_FOUND)


class SnapshotNotFoundError(ProxmoxError):
    """Snapshot introuvable."""

    def __init__(self, snapname: str, vmid: int):
        super().__init__(
            f"Snapshot '{snapname}' introuvable pour VM/LXC {vmid}",
            ErrorCode.SNAPSHOT_NOT_FOUND,
        )


class StorageNotFoundError(ProxmoxError):
    """Storage introuvable."""

    def __init__(self, storage: str, node: str | None = None):
        location = f" sur le nœud '{node}'" if node else ""
        super().__init__(f"Storage '{storage}' introuvable{location}", ErrorCode.STORAGE_NOT_FOUND)


class PermissionDeniedError(ProxmoxError):
    """Droits insuffisants pour l'opération."""

    def __init__(self, message: str = "Droits insuffisants pour cette opération"):
        super().__init__(message, ErrorCode.PERMISSION_DENIED)


class TaskFailedError(ProxmoxError):
    """Tâche Proxmox échouée."""

    def __init__(self, upid: str, message: str | None = None):
        error_msg = f"Tâche {upid} échouée"
        if message:
            error_msg += f": {message}"
        super().__init__(error_msg, ErrorCode.TASK_FAILED)


class InvalidStateError(ProxmoxError):
    """État invalide pour l'opération demandée."""

    def __init__(self, message: str):
        super().__init__(message, ErrorCode.INVALID_STATE)


# =============================================================================
# Exceptions SSH
# =============================================================================


class SSHError(ProxmoxError):
    """Exception de base pour les erreurs SSH."""

    def __init__(self, message: str, error_code: ErrorCode = ErrorCode.SSH_CONNECTION_ERROR):
        super().__init__(message, error_code)


class SSHAuthenticationError(SSHError):
    """Erreur d'authentification SSH."""

    def __init__(self, message: str = "Échec de l'authentification SSH"):
        super().__init__(message, ErrorCode.SSH_AUTH_FAILED)


class SSHCommandError(SSHError):
    """Erreur lors de l'exécution d'une commande SSH."""

    def __init__(self, command: str, exit_code: int, stderr: str = ""):
        message = f"Commande '{command}' échouée (code {exit_code})"
        if stderr:
            message += f": {stderr[:200]}"
        super().__init__(message, ErrorCode.SSH_COMMAND_FAILED)
        self.exit_code = exit_code
        self.stderr = stderr


class SSHFileNotFoundError(SSHError):
    """Fichier distant introuvable."""

    def __init__(self, path: str):
        super().__init__(f"Fichier '{path}' introuvable", ErrorCode.SSH_FILE_NOT_FOUND)


class SSHTimeoutError(SSHError):
    """Timeout lors de l'opération SSH."""

    def __init__(self, operation: str = "connexion"):
        super().__init__(f"Timeout SSH lors de {operation}", ErrorCode.SSH_TIMEOUT)
