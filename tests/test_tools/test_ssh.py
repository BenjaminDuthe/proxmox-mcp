"""Tests pour les tools SSH."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from proxmox_mcp.exceptions import SSHError, SSHFileNotFoundError
from proxmox_mcp.ssh_client import SSHClient
from proxmox_mcp.tools.ssh import (
    fix_apt_repos,
    ssh_execute,
    ssh_read_file,
    ssh_write_file,
)


@pytest.fixture
def mock_ssh_client() -> SSHClient:
    """Client SSH mocké pour les tests."""
    client = MagicMock(spec=SSHClient)
    client.execute = AsyncMock()
    client.read_file = AsyncMock()
    client.write_file = AsyncMock()
    return client


class TestSSHExecute:
    """Tests pour ssh_execute."""

    @pytest.mark.asyncio
    async def test_execute_success(self, mock_ssh_client: SSHClient) -> None:
        """ssh_execute retourne le résultat d'une commande réussie."""
        mock_ssh_client.execute = AsyncMock(
            return_value={
                "command": "hostname",
                "exit_code": 0,
                "stdout": "pve1\n",
                "stderr": "",
                "duration_ms": 42,
            }
        )

        result = await ssh_execute(mock_ssh_client, "pve1", "hostname")

        assert result["success"] is True
        assert result["data"]["exit_code"] == 0
        assert result["data"]["stdout"] == "pve1\n"

    @pytest.mark.asyncio
    async def test_execute_command_fails(self, mock_ssh_client: SSHClient) -> None:
        """ssh_execute retourne success=False si la commande échoue."""
        mock_ssh_client.execute = AsyncMock(
            return_value={
                "command": "invalid_command",
                "exit_code": 127,
                "stdout": "",
                "stderr": "command not found",
                "duration_ms": 10,
            }
        )

        result = await ssh_execute(mock_ssh_client, "pve1", "invalid_command")

        assert result["success"] is False
        assert result["data"]["exit_code"] == 127

    @pytest.mark.asyncio
    async def test_execute_ssh_error(self, mock_ssh_client: SSHClient) -> None:
        """ssh_execute gère les erreurs SSH."""
        mock_ssh_client.execute = AsyncMock(side_effect=SSHError("Connection failed"))

        result = await ssh_execute(mock_ssh_client, "pve1", "hostname")

        assert result["success"] is False
        assert "error" in result
        assert "SSH_CONNECTION_ERROR" in result["error_code"]


class TestSSHReadFile:
    """Tests pour ssh_read_file."""

    @pytest.mark.asyncio
    async def test_read_file_success(self, mock_ssh_client: SSHClient) -> None:
        """ssh_read_file lit le contenu d'un fichier."""
        mock_ssh_client.read_file = AsyncMock(
            return_value={
                "path": "/etc/hostname",
                "exists": True,
                "size": 5,
                "content": "pve1\n",
            }
        )

        result = await ssh_read_file(mock_ssh_client, "pve1", "/etc/hostname")

        assert result["success"] is True
        assert result["data"]["content"] == "pve1\n"

    @pytest.mark.asyncio
    async def test_read_file_not_found(self, mock_ssh_client: SSHClient) -> None:
        """ssh_read_file gère les fichiers inexistants."""
        mock_ssh_client.read_file = AsyncMock(
            side_effect=SSHFileNotFoundError("/etc/missing")
        )

        result = await ssh_read_file(mock_ssh_client, "pve1", "/etc/missing")

        assert result["success"] is False
        assert "SSH_FILE_NOT_FOUND" in result["error_code"]


class TestSSHWriteFile:
    """Tests pour ssh_write_file."""

    @pytest.mark.asyncio
    async def test_write_file_with_backup(self, mock_ssh_client: SSHClient) -> None:
        """ssh_write_file crée un backup et écrit le fichier."""
        mock_ssh_client.write_file = AsyncMock(
            return_value={
                "path": "/etc/test.conf",
                "backup_path": "/etc/test.conf.bak.20240115",
                "size": 20,
                "success": True,
            }
        )

        result = await ssh_write_file(
            mock_ssh_client,
            "pve1",
            "/etc/test.conf",
            "test content",
            backup=True,
        )

        assert result["success"] is True
        assert result["data"]["backup_path"] is not None

    @pytest.mark.asyncio
    async def test_write_file_without_backup(self, mock_ssh_client: SSHClient) -> None:
        """ssh_write_file peut écrire sans backup."""
        mock_ssh_client.write_file = AsyncMock(
            return_value={
                "path": "/etc/test.conf",
                "backup_path": None,
                "size": 20,
                "success": True,
            }
        )

        result = await ssh_write_file(
            mock_ssh_client,
            "pve1",
            "/etc/test.conf",
            "test content",
            backup=False,
        )

        assert result["success"] is True
        assert result["data"]["backup_path"] is None


class TestFixAptRepos:
    """Tests pour fix_apt_repos."""

    @pytest.mark.asyncio
    async def test_fix_apt_repos_fresh_install(self, mock_ssh_client: SSHClient) -> None:
        """fix_apt_repos configure les dépôts sur une installation fraîche."""

        # Séquence des appels execute
        execute_calls = [
            # Check enterprise file exists
            {"stdout": "EXISTS", "exit_code": 0, "stderr": "", "command": "", "duration_ms": 0},
            # Get OS codename
            {"stdout": "bookworm\n", "exit_code": 0, "stderr": "", "command": "", "duration_ms": 0},
            # Check no-subscription not configured
            {"stdout": "", "exit_code": 1, "stderr": "", "command": "", "duration_ms": 0},
        ]
        mock_ssh_client.execute = AsyncMock(side_effect=execute_calls)

        mock_ssh_client.read_file = AsyncMock(
            return_value={
                "path": "/etc/apt/sources.list.d/pve-enterprise.list",
                "content": "deb https://enterprise.proxmox.com/debian/pve bookworm pve-enterprise",
                "exists": True,
                "size": 100,
            }
        )

        mock_ssh_client.write_file = AsyncMock(
            return_value={
                "path": "",
                "backup_path": "/etc/apt/sources.list.d/pve-enterprise.list.bak",
                "size": 100,
                "success": True,
            }
        )

        result = await fix_apt_repos(mock_ssh_client, "pve1")

        assert result["success"] is True
        assert len(result["data"]["changes"]) > 0
        assert result["data"]["apt_update_required"] is True

    @pytest.mark.asyncio
    async def test_fix_apt_repos_already_configured(
        self, mock_ssh_client: SSHClient
    ) -> None:
        """fix_apt_repos ne fait rien si déjà configuré."""

        # Séquence des appels execute
        execute_calls = [
            # Check enterprise file exists
            {"stdout": "EXISTS", "exit_code": 0, "stderr": "", "command": "", "duration_ms": 0},
            # Get OS codename
            {"stdout": "bookworm\n", "exit_code": 0, "stderr": "", "command": "", "duration_ms": 0},
            # Check no-subscription already configured
            {"stdout": "CONFIGURED", "exit_code": 0, "stderr": "", "command": "", "duration_ms": 0},
        ]
        mock_ssh_client.execute = AsyncMock(side_effect=execute_calls)

        # Enterprise already commented
        mock_ssh_client.read_file = AsyncMock(
            return_value={
                "path": "/etc/apt/sources.list.d/pve-enterprise.list",
                "content": "# Disabled\n# deb https://enterprise.proxmox.com/debian/pve bookworm pve-enterprise",
                "exists": True,
                "size": 100,
            }
        )

        result = await fix_apt_repos(mock_ssh_client, "pve1")

        assert result["success"] is True
        assert len(result["data"]["changes"]) == 0
        assert result["data"]["apt_update_required"] is False
