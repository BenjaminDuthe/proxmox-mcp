"""Client async pour l'API Proxmox VE."""

import logging
import ssl
import time
from typing import Any

import httpx

from proxmox_mcp.config import ProxmoxConfig
from proxmox_mcp.exceptions import (
    AuthenticationError,
    ConnectionError,
    PermissionDeniedError,
    ProxmoxError,
)

logger = logging.getLogger(__name__)

# Durée de validité du ticket (2h) avec marge de sécurité (5 min)
TICKET_VALIDITY_SECONDS = 2 * 60 * 60 - 5 * 60


def _create_ssl_context(verify: bool) -> ssl.SSLContext | bool:
    """Crée un contexte SSL approprié.

    Args:
        verify: Si True, vérifie les certificats. Si False, désactive la vérification.

    Returns:
        Contexte SSL ou False pour désactiver complètement
    """
    if verify:
        return True

    # Créer un contexte SSL qui n'effectue aucune vérification
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


class ProxmoxClient:
    """Client async pour interagir avec l'API Proxmox VE.

    Supporte deux modes d'authentification:
    - Token API (recommandé): utilise token_id et token_secret
    - User/Password: obtient un ticket avec renouvellement automatique

    Args:
        config: Configuration de connexion Proxmox

    Example:
        ```python
        config = ProxmoxConfig(
            host="192.168.1.10",
            token_id="root@pam!mcp",
            token_secret="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
        )
        async with ProxmoxClient(config) as client:
            nodes = await client.get("/nodes")
        ```
    """

    def __init__(self, config: ProxmoxConfig):
        self.config = config
        self._client: httpx.AsyncClient | None = None

        # Auth par ticket (user/password)
        self._ticket: str | None = None
        self._csrf_token: str | None = None
        self._ticket_expires: float = 0

    async def __aenter__(self) -> "ProxmoxClient":
        """Initialise le client HTTP async."""
        ssl_context = _create_ssl_context(self.config.verify_ssl)
        self._client = httpx.AsyncClient(
            base_url=self.config.base_url,
            verify=ssl_context,
            timeout=httpx.Timeout(self.config.timeout, connect=10.0),
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
        )
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Ferme le client HTTP."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _ensure_auth(self) -> None:
        """S'assure qu'on a une authentification valide.

        Pour l'auth par token, rien à faire.
        Pour l'auth par ticket, vérifie et renouvelle si nécessaire.

        Raises:
            AuthenticationError: Si l'authentification échoue
        """
        if self.config.use_token_auth:
            return

        # Vérifier si le ticket est encore valide
        if self._ticket and time.time() < self._ticket_expires:
            return

        # Obtenir un nouveau ticket
        await self._login()

    async def _login(self) -> None:
        """Authentification par user/password pour obtenir un ticket.

        Raises:
            AuthenticationError: Si les credentials sont invalides
            ConnectionError: Si le serveur est injoignable
        """
        if not self._client:
            raise ConnectionError("Client HTTP non initialisé")

        logger.debug("Authentification par user/password...")

        try:
            response = await self._client.post(
                "/access/ticket",
                data={
                    "username": self.config.user,
                    "password": self.config.password,
                },
            )
        except httpx.ConnectError as e:
            raise ConnectionError(f"Impossible de se connecter à {self.config.host}: {e}")
        except httpx.TimeoutException:
            raise ConnectionError(f"Timeout lors de la connexion à {self.config.host}")

        if response.status_code == 401:
            raise AuthenticationError("Credentials invalides")
        if response.status_code != 200:
            raise AuthenticationError(f"Erreur d'authentification: {response.status_code}")

        data = response.json().get("data", {})
        self._ticket = data.get("ticket")
        self._csrf_token = data.get("CSRFPreventionToken")
        self._ticket_expires = time.time() + TICKET_VALIDITY_SECONDS

        if not self._ticket:
            raise AuthenticationError("Ticket non reçu dans la réponse")

        logger.debug("Authentification réussie, ticket obtenu")

    def _get_headers(self) -> dict[str, str]:
        """Retourne les headers d'authentification appropriés.

        Returns:
            Headers HTTP pour l'authentification
        """
        if self.config.use_token_auth:
            return {
                "Authorization": f"PVEAPIToken={self.config.token_id}={self.config.token_secret}"
            }
        else:
            headers = {"Cookie": f"PVEAuthCookie={self._ticket}"}
            if self._csrf_token:
                headers["CSRFPreventionToken"] = self._csrf_token
            return headers

    async def request(
        self,
        method: str,
        path: str,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Effectue une requête à l'API Proxmox.

        Args:
            method: Méthode HTTP (GET, POST, PUT, DELETE)
            path: Chemin de l'endpoint (ex: /nodes)
            data: Données pour POST/PUT
            params: Paramètres de query string

        Returns:
            Réponse JSON de l'API (clé "data" extraite)

        Raises:
            ConnectionError: Si le serveur est injoignable
            AuthenticationError: Si l'authentification échoue
            PermissionDeniedError: Si les droits sont insuffisants
            ProxmoxError: Pour les autres erreurs API
        """
        if not self._client:
            raise ConnectionError("Client HTTP non initialisé. Utilisez 'async with'.")

        await self._ensure_auth()

        # Normaliser le path
        if not path.startswith("/"):
            path = f"/{path}"

        headers = self._get_headers()

        logger.debug(f"API Request: {method} {path}")

        try:
            response = await self._client.request(
                method=method,
                url=path,
                headers=headers,
                data=data,
                params=params,
            )
        except httpx.ConnectError as e:
            raise ConnectionError(f"Connexion perdue avec {self.config.host}: {e}")
        except httpx.TimeoutException:
            raise ConnectionError(f"Timeout lors de la requête vers {path}")

        # Gérer les codes d'erreur HTTP
        if response.status_code == 401:
            # Token expiré ou invalide, réessayer une fois après login
            if not self.config.use_token_auth:
                self._ticket = None
                await self._ensure_auth()
                response = await self._client.request(
                    method=method,
                    url=path,
                    headers=self._get_headers(),
                    data=data,
                    params=params,
                )
                if response.status_code == 401:
                    raise AuthenticationError("Session expirée, impossible de se reconnecter")
            else:
                raise AuthenticationError("Token API invalide ou expiré")

        if response.status_code == 403:
            raise PermissionDeniedError(f"Accès refusé pour {path}")

        if response.status_code == 404:
            # Retourner None pour les 404, le caller gèrera
            return {"data": None, "_status": 404}

        if response.status_code >= 400:
            error_msg = response.text
            try:
                error_data = response.json()
                if "errors" in error_data:
                    error_msg = str(error_data["errors"])
            except Exception:
                pass
            raise ProxmoxError(f"Erreur API ({response.status_code}): {error_msg}")

        # Parser la réponse JSON
        try:
            result = response.json()
        except Exception:
            raise ProxmoxError(f"Réponse JSON invalide: {response.text[:200]}")

        logger.debug(f"API Response: {response.status_code}")

        return result

    async def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Effectue une requête GET.

        Args:
            path: Chemin de l'endpoint
            params: Paramètres de query string optionnels

        Returns:
            Réponse JSON de l'API
        """
        return await self.request("GET", path, params=params)

    async def post(self, path: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        """Effectue une requête POST.

        Args:
            path: Chemin de l'endpoint
            data: Données à envoyer

        Returns:
            Réponse JSON de l'API
        """
        return await self.request("POST", path, data=data)

    async def put(self, path: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        """Effectue une requête PUT.

        Args:
            path: Chemin de l'endpoint
            data: Données à envoyer

        Returns:
            Réponse JSON de l'API
        """
        return await self.request("PUT", path, data=data)

    async def delete(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Effectue une requête DELETE.

        Args:
            path: Chemin de l'endpoint
            params: Paramètres de query string optionnels

        Returns:
            Réponse JSON de l'API
        """
        return await self.request("DELETE", path, params=params)


# Instance globale du client (initialisée par le serveur)
_client: ProxmoxClient | None = None


def get_client() -> ProxmoxClient:
    """Retourne l'instance globale du client Proxmox.

    Returns:
        Client Proxmox configuré

    Raises:
        RuntimeError: Si le client n'est pas initialisé
    """
    if _client is None:
        raise RuntimeError("Client Proxmox non initialisé. Appelez init_client() d'abord.")
    return _client


def set_client(client: ProxmoxClient) -> None:
    """Définit l'instance globale du client Proxmox.

    Args:
        client: Instance du client à utiliser
    """
    global _client
    _client = client
