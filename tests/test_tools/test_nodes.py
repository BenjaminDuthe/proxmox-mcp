"""Tests pour les tools de gestion des nœuds."""

from typing import Any
from unittest.mock import AsyncMock

import pytest

from proxmox_mcp.client import ProxmoxClient
from proxmox_mcp.tools.nodes import get_node_status, list_nodes


class TestListNodes:
    """Tests pour list_nodes."""

    @pytest.mark.asyncio
    async def test_list_nodes_success(
        self,
        mock_client: ProxmoxClient,
        mock_nodes_data: list[dict[str, Any]],
    ) -> None:
        """list_nodes retourne tous les nœuds du cluster."""
        mock_client.get = AsyncMock(return_value={"data": mock_nodes_data})

        result = await list_nodes(mock_client)

        assert result["success"] is True
        assert result["count"] == 2
        assert len(result["data"]) == 2
        assert result["data"][0]["node"] == "pve1"
        assert result["data"][1]["node"] == "pve2"

    @pytest.mark.asyncio
    async def test_list_nodes_empty(self, mock_client: ProxmoxClient) -> None:
        """list_nodes retourne une liste vide si aucun nœud."""
        mock_client.get = AsyncMock(return_value={"data": []})

        result = await list_nodes(mock_client)

        assert result["success"] is True
        assert result["count"] == 0
        assert result["data"] == []

    @pytest.mark.asyncio
    async def test_list_nodes_fields(
        self,
        mock_client: ProxmoxClient,
        mock_nodes_data: list[dict[str, Any]],
    ) -> None:
        """list_nodes inclut les champs attendus pour chaque nœud."""
        mock_client.get = AsyncMock(return_value={"data": mock_nodes_data})

        result = await list_nodes(mock_client)

        node = result["data"][0]
        assert node["status"] == "online"
        assert node["cpu"] == 0.15
        assert node["maxcpu"] == 8
        assert node["maxmem"] == 17179869184


class TestGetNodeStatus:
    """Tests pour get_node_status."""

    @pytest.mark.asyncio
    async def test_get_node_status_success(self, mock_client: ProxmoxClient) -> None:
        """get_node_status retourne les métriques détaillées du nœud."""
        mock_client.get = AsyncMock(
            return_value={
                "data": {
                    "cpu": 0.15,
                    "cpuinfo": {"cpus": 8, "cores": 4, "sockets": 2, "model": "Intel Xeon"},
                    "memory": {"used": 8589934592, "total": 17179869184},
                    "rootfs": {"used": 107374182400, "total": 536870912000},
                    "uptime": 864000,
                    "kversion": "Linux 6.2.16-3-pve",
                    "pveversion": "pve-manager/8.1.3",
                }
            }
        )

        result = await get_node_status(mock_client, "pve1")

        assert result["success"] is True
        assert result["data"]["node"] == "pve1"
        assert result["data"]["status"] == "online"
        assert result["data"]["cpu_model"] == "Intel Xeon"
        assert result["data"]["kernel_version"] == "Linux 6.2.16-3-pve"
        assert result["data"]["pve_version"] == "pve-manager/8.1.3"
        assert "cpu_percent" in result["data"]
        assert "mem_percent" in result["data"]

    @pytest.mark.asyncio
    async def test_get_node_status_not_found(self, mock_client: ProxmoxClient) -> None:
        """get_node_status retourne une erreur si le nœud n'existe pas."""
        mock_client.get = AsyncMock(return_value={"data": None})

        result = await get_node_status(mock_client, "nonexistent")

        assert result["success"] is False
        assert result["error_code"] == "NODE_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_get_node_status_minimal_data(self, mock_client: ProxmoxClient) -> None:
        """get_node_status gère les données minimales sans cpuinfo ni kversion."""
        mock_client.get = AsyncMock(
            return_value={
                "data": {
                    "cpu": 0.0,
                    "memory": {"used": 0, "total": 0},
                    "rootfs": {"used": 0, "total": 0},
                    "uptime": 0,
                }
            }
        )

        result = await get_node_status(mock_client, "pve1")

        assert result["success"] is True
        assert "cpu_model" not in result["data"]
        assert "kernel_version" not in result["data"]
