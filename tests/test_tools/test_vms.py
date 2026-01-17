"""Tests pour les tools de gestion des VMs."""

from typing import Any
from unittest.mock import AsyncMock

import pytest

from proxmox_mcp.client import ProxmoxClient
from proxmox_mcp.tools.vms import (
    destroy_vm,
    get_vm_details,
    list_vms,
    reboot_vm,
    shutdown_vm,
    start_vm,
    stop_vm,
)


class TestListVMs:
    """Tests pour list_vms."""

    @pytest.mark.asyncio
    async def test_list_vms_all_nodes(
        self,
        mock_client: ProxmoxClient,
        mock_nodes_data: list[dict[str, Any]],
        mock_vm_list: list[dict[str, Any]],
    ) -> None:
        """list_vms retourne les VMs de tous les nœuds."""
        mock_client.get = AsyncMock(
            side_effect=[
                {"data": mock_nodes_data},  # /nodes
                {"data": mock_vm_list},  # /nodes/pve1/qemu
                {"data": []},  # /nodes/pve2/qemu
            ]
        )

        result = await list_vms(mock_client)

        assert result["success"] is True
        assert result["count"] == 3
        assert len(result["data"]) == 3

    @pytest.mark.asyncio
    async def test_list_vms_single_node(
        self,
        mock_client: ProxmoxClient,
        mock_vm_list: list[dict[str, Any]],
    ) -> None:
        """list_vms filtre par nœud quand spécifié."""
        mock_client.get = AsyncMock(return_value={"data": mock_vm_list})

        result = await list_vms(mock_client, node="pve1")

        assert result["success"] is True
        assert result["count"] == 3
        # Vérifie qu'on n'a pas appelé /nodes
        mock_client.get.assert_called_once_with("/nodes/pve1/qemu")

    @pytest.mark.asyncio
    async def test_list_vms_empty(self, mock_client: ProxmoxClient) -> None:
        """list_vms retourne une liste vide si aucune VM."""
        mock_client.get = AsyncMock(
            side_effect=[
                {"data": [{"node": "pve1"}]},  # /nodes
                {"data": []},  # /nodes/pve1/qemu
            ]
        )

        result = await list_vms(mock_client)

        assert result["success"] is True
        assert result["count"] == 0
        assert result["data"] == []


class TestGetVMDetails:
    """Tests pour get_vm_details."""

    @pytest.mark.asyncio
    async def test_get_vm_details_success(self, mock_client: ProxmoxClient) -> None:
        """get_vm_details retourne la configuration complète."""
        mock_config = {
            "name": "web-server",
            "description": "Serveur web production",
            "cores": 2,
            "memory": 2048,
            "ostype": "l26",
            "boot": "order=scsi0",
            "net0": "virtio=AA:BB:CC:DD:EE:FF,bridge=vmbr0",
            "scsi0": "local-lvm:vm-100-disk-0,size=50G",
        }
        mock_status = {
            "status": "running",
            "cpu": 0.05,
            "mem": 1073741824,
            "uptime": 86400,
            "pid": 12345,
            "qmpstatus": "running",
        }

        mock_client.get = AsyncMock(
            side_effect=[
                {"data": mock_config},
                {"data": mock_status},
            ]
        )

        result = await get_vm_details(mock_client, "pve1", 100)

        assert result["success"] is True
        assert result["data"]["name"] == "web-server"
        assert result["data"]["cores"] == 2
        assert result["data"]["status"] == "running"
        assert "net0" in result["data"]["networks"]
        assert "scsi0" in result["data"]["disks"]

    @pytest.mark.asyncio
    async def test_get_vm_details_not_found(self, mock_client: ProxmoxClient) -> None:
        """get_vm_details retourne une erreur si la VM n'existe pas."""
        mock_client.get = AsyncMock(return_value={"data": None, "_status": 404})

        result = await get_vm_details(mock_client, "pve1", 999)

        assert result["success"] is False
        assert result["error_code"] == "VM_NOT_FOUND"


class TestStartVM:
    """Tests pour start_vm."""

    @pytest.mark.asyncio
    async def test_start_vm_success(self, mock_client: ProxmoxClient) -> None:
        """start_vm démarre une VM arrêtée."""
        mock_client.get = AsyncMock(return_value={"data": {"status": "stopped"}})
        mock_client.post = AsyncMock(
            return_value={"data": "UPID:pve1:00001234:xxx:qmstart:100:root@pam:"}
        )

        result = await start_vm(mock_client, "pve1", 100)

        assert result["success"] is True
        assert "task_id" in result
        assert result["vmid"] == 100

    @pytest.mark.asyncio
    async def test_start_vm_already_running(self, mock_client: ProxmoxClient) -> None:
        """start_vm échoue si la VM est déjà running."""
        mock_client.get = AsyncMock(return_value={"data": {"status": "running"}})

        result = await start_vm(mock_client, "pve1", 100)

        assert result["success"] is False
        assert result["error_code"] == "INVALID_STATE"

    @pytest.mark.asyncio
    async def test_start_lxc_container(self, mock_client: ProxmoxClient) -> None:
        """start_vm fonctionne pour les conteneurs LXC."""
        mock_client.get = AsyncMock(return_value={"data": {"status": "stopped"}})
        mock_client.post = AsyncMock(return_value={"data": "UPID:pve1:xxx"})

        result = await start_vm(mock_client, "pve1", 200, vm_type="lxc")

        assert result["success"] is True
        mock_client.get.assert_called_with("/nodes/pve1/lxc/200/status/current")


class TestStopVM:
    """Tests pour stop_vm."""

    @pytest.mark.asyncio
    async def test_stop_vm_success(self, mock_client: ProxmoxClient) -> None:
        """stop_vm arrête une VM running."""
        mock_client.get = AsyncMock(return_value={"data": {"status": "running"}})
        mock_client.post = AsyncMock(return_value={"data": "UPID:pve1:xxx"})

        result = await stop_vm(mock_client, "pve1", 100)

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_stop_vm_already_stopped(self, mock_client: ProxmoxClient) -> None:
        """stop_vm échoue si la VM est déjà arrêtée."""
        mock_client.get = AsyncMock(return_value={"data": {"status": "stopped"}})

        result = await stop_vm(mock_client, "pve1", 100)

        assert result["success"] is False
        assert result["error_code"] == "INVALID_STATE"


class TestShutdownVM:
    """Tests pour shutdown_vm."""

    @pytest.mark.asyncio
    async def test_shutdown_vm_success(self, mock_client: ProxmoxClient) -> None:
        """shutdown_vm fait un arrêt gracieux."""
        mock_client.get = AsyncMock(return_value={"data": {"status": "running"}})
        mock_client.post = AsyncMock(return_value={"data": "UPID:pve1:xxx"})

        result = await shutdown_vm(mock_client, "pve1", 100)

        assert result["success"] is True
        mock_client.post.assert_called_with("/nodes/pve1/qemu/100/status/shutdown")


class TestRebootVM:
    """Tests pour reboot_vm."""

    @pytest.mark.asyncio
    async def test_reboot_vm_success(self, mock_client: ProxmoxClient) -> None:
        """reboot_vm redémarre une VM running."""
        mock_client.get = AsyncMock(return_value={"data": {"status": "running"}})
        mock_client.post = AsyncMock(return_value={"data": "UPID:pve1:xxx"})

        result = await reboot_vm(mock_client, "pve1", 100)

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_reboot_vm_stopped_fails(self, mock_client: ProxmoxClient) -> None:
        """reboot_vm échoue si la VM est arrêtée."""
        mock_client.get = AsyncMock(return_value={"data": {"status": "stopped"}})

        result = await reboot_vm(mock_client, "pve1", 100)

        assert result["success"] is False
        assert result["error_code"] == "INVALID_STATE"


class TestDestroyVM:
    """Tests pour destroy_vm."""

    @pytest.mark.asyncio
    async def test_destroy_vm_success(self, mock_client: ProxmoxClient) -> None:
        """destroy_vm supprime une VM arrêtée."""
        mock_client.get = AsyncMock(return_value={"data": {"status": "stopped"}})
        mock_client.delete = AsyncMock(return_value={"data": "UPID:pve1:xxx"})

        result = await destroy_vm(mock_client, "pve1", 100)

        assert result["success"] is True
        assert "warning" in result  # Avertissement sur l'irréversibilité

    @pytest.mark.asyncio
    async def test_destroy_vm_running_fails(self, mock_client: ProxmoxClient) -> None:
        """destroy_vm échoue si la VM est running."""
        mock_client.get = AsyncMock(return_value={"data": {"status": "running"}})

        result = await destroy_vm(mock_client, "pve1", 100)

        assert result["success"] is False
        assert result["error_code"] == "INVALID_STATE"
        assert "arrêtée" in result["error"]

    @pytest.mark.asyncio
    async def test_destroy_vm_not_found(self, mock_client: ProxmoxClient) -> None:
        """destroy_vm échoue si la VM n'existe pas."""
        mock_client.get = AsyncMock(return_value={"data": None, "_status": 404})

        result = await destroy_vm(mock_client, "pve1", 999)

        assert result["success"] is False
        assert result["error_code"] == "VM_NOT_FOUND"
