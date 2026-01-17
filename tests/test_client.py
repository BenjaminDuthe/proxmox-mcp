"""Tests pour le client Proxmox async."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from proxmox_mcp.client import ProxmoxClient
from proxmox_mcp.config import ProxmoxConfig
from proxmox_mcp.exceptions import AuthenticationError, ConnectionError


class TestProxmoxClientInit:
    """Tests d'initialisation du client."""

    def test_client_init_with_token(self, mock_config: ProxmoxConfig) -> None:
        """Le client s'initialise correctement avec un token."""
        client = ProxmoxClient(mock_config)
        assert client.config == mock_config
        assert client._ticket is None
        assert client._csrf_token is None

    def test_client_init_with_password(self, mock_config_password: ProxmoxConfig) -> None:
        """Le client s'initialise correctement avec user/password."""
        client = ProxmoxClient(mock_config_password)
        assert client.config == mock_config_password
        assert not client.config.use_token_auth


class TestProxmoxClientAuth:
    """Tests d'authentification."""

    def test_token_auth_headers(self, mock_config: ProxmoxConfig) -> None:
        """Les headers token sont correctement générés."""
        client = ProxmoxClient(mock_config)
        headers = client._get_headers()

        expected = f"PVEAPIToken={mock_config.token_id}={mock_config.token_secret}"
        assert headers["Authorization"] == expected

    def test_ticket_auth_headers(self, mock_config_password: ProxmoxConfig) -> None:
        """Les headers ticket sont correctement générés."""
        client = ProxmoxClient(mock_config_password)
        client._ticket = "test-ticket"
        client._csrf_token = "test-csrf"

        headers = client._get_headers()

        assert headers["Cookie"] == "PVEAuthCookie=test-ticket"
        assert headers["CSRFPreventionToken"] == "test-csrf"


class TestProxmoxClientRequests:
    """Tests des requêtes HTTP."""

    @pytest.mark.asyncio
    async def test_get_request(self, mock_config: ProxmoxConfig) -> None:
        """Une requête GET fonctionne correctement."""
        client = ProxmoxClient(mock_config)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [{"node": "pve1"}]}

        mock_http_client = AsyncMock()
        mock_http_client.request = AsyncMock(return_value=mock_response)

        client._client = mock_http_client

        result = await client.get("/nodes")

        assert result["data"] == [{"node": "pve1"}]
        mock_http_client.request.assert_called_once()

    @pytest.mark.asyncio
    async def test_post_request(self, mock_config: ProxmoxConfig) -> None:
        """Une requête POST fonctionne correctement."""
        client = ProxmoxClient(mock_config)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": "UPID:pve1:xxx"}

        mock_http_client = AsyncMock()
        mock_http_client.request = AsyncMock(return_value=mock_response)

        client._client = mock_http_client

        result = await client.post("/nodes/pve1/qemu/100/status/start")

        assert result["data"] == "UPID:pve1:xxx"

    @pytest.mark.asyncio
    async def test_connection_error(self, mock_config: ProxmoxConfig) -> None:
        """Une erreur de connexion est correctement gérée."""
        client = ProxmoxClient(mock_config)

        mock_http_client = AsyncMock()
        mock_http_client.request = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))

        client._client = mock_http_client

        with pytest.raises(ConnectionError):
            await client.get("/nodes")

    @pytest.mark.asyncio
    async def test_auth_error(self, mock_config: ProxmoxConfig) -> None:
        """Une erreur 401 lève AuthenticationError."""
        client = ProxmoxClient(mock_config)

        mock_response = MagicMock()
        mock_response.status_code = 401

        mock_http_client = AsyncMock()
        mock_http_client.request = AsyncMock(return_value=mock_response)

        client._client = mock_http_client

        with pytest.raises(AuthenticationError):
            await client.get("/nodes")

    @pytest.mark.asyncio
    async def test_404_returns_none_data(self, mock_config: ProxmoxConfig) -> None:
        """Un 404 retourne data=None pour permettre la gestion par le caller."""
        client = ProxmoxClient(mock_config)

        mock_response = MagicMock()
        mock_response.status_code = 404

        mock_http_client = AsyncMock()
        mock_http_client.request = AsyncMock(return_value=mock_response)

        client._client = mock_http_client

        result = await client.get("/nodes/unknown/qemu/999")

        assert result["data"] is None
        assert result["_status"] == 404


class TestProxmoxClientContextManager:
    """Tests du context manager."""

    @pytest.mark.asyncio
    async def test_context_manager(self, mock_config: ProxmoxConfig) -> None:
        """Le context manager initialise et ferme le client HTTP."""
        with patch("proxmox_mcp.client.httpx.AsyncClient") as mock_class:
            mock_instance = AsyncMock()
            mock_class.return_value = mock_instance

            async with ProxmoxClient(mock_config) as client:
                assert client._client is not None

            mock_instance.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_request_without_context_manager_raises(
        self, mock_config: ProxmoxConfig
    ) -> None:
        """Une requête sans context manager lève une erreur."""
        client = ProxmoxClient(mock_config)

        with pytest.raises(ConnectionError) as exc_info:
            await client.get("/nodes")

        assert "non initialisé" in str(exc_info.value)
