"""Fixtures pytest pour les tests du serveur MCP Proxmox."""

from typing import Any
from unittest.mock import AsyncMock

import pytest

from proxmox_mcp.client import ProxmoxClient
from proxmox_mcp.config import ProxmoxConfig


@pytest.fixture
def mock_config() -> ProxmoxConfig:
    """Configuration de test avec authentification par token."""
    return ProxmoxConfig(
        host="test.local",
        port=8006,
        verify_ssl=False,
        timeout=30,
        token_id="test@pam!test-token",
        token_secret="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    )


@pytest.fixture
def mock_config_password() -> ProxmoxConfig:
    """Configuration de test avec authentification par mot de passe."""
    return ProxmoxConfig(
        host="test.local",
        port=8006,
        verify_ssl=False,
        timeout=30,
        user="root@pam",
        password="testpassword",
    )


@pytest.fixture
def mock_client(mock_config: ProxmoxConfig) -> ProxmoxClient:
    """Client Proxmox mocké pour les tests."""
    client = ProxmoxClient(mock_config)
    client.get = AsyncMock()
    client.post = AsyncMock()
    client.put = AsyncMock()
    client.delete = AsyncMock()
    return client


@pytest.fixture
def mock_nodes_data() -> list[dict[str, Any]]:
    """Données de test pour les nœuds."""
    return [
        {
            "node": "pve1",
            "status": "online",
            "cpu": 0.15,
            "maxcpu": 8,
            "mem": 8589934592,  # 8 GB
            "maxmem": 17179869184,  # 16 GB
            "disk": 107374182400,  # 100 GB
            "maxdisk": 536870912000,  # 500 GB
            "uptime": 864000,  # 10 jours
        },
        {
            "node": "pve2",
            "status": "online",
            "cpu": 0.42,
            "maxcpu": 16,
            "mem": 34359738368,  # 32 GB
            "maxmem": 68719476736,  # 64 GB
            "disk": 214748364800,  # 200 GB
            "maxdisk": 1073741824000,  # 1 TB
            "uptime": 432000,  # 5 jours
        },
    ]


@pytest.fixture
def mock_vm_list() -> list[dict[str, Any]]:
    """Données de test pour les VMs."""
    return [
        {
            "vmid": 100,
            "name": "web-server",
            "status": "running",
            "cpu": 0.05,
            "cpus": 2,
            "mem": 1073741824,  # 1 GB
            "maxmem": 2147483648,  # 2 GB
            "disk": 10737418240,  # 10 GB
            "maxdisk": 53687091200,  # 50 GB
            "uptime": 86400,
            "netin": 1000000,
            "netout": 500000,
        },
        {
            "vmid": 101,
            "name": "database",
            "status": "running",
            "cpu": 0.25,
            "cpus": 4,
            "mem": 4294967296,  # 4 GB
            "maxmem": 8589934592,  # 8 GB
            "disk": 53687091200,  # 50 GB
            "maxdisk": 107374182400,  # 100 GB
            "uptime": 172800,
            "netin": 5000000,
            "netout": 2500000,
        },
        {
            "vmid": 102,
            "name": "test-vm",
            "status": "stopped",
            "cpu": 0,
            "cpus": 1,
            "mem": 0,
            "maxmem": 1073741824,  # 1 GB
            "disk": 0,
            "maxdisk": 21474836480,  # 20 GB
            "uptime": 0,
            "netin": 0,
            "netout": 0,
        },
    ]


@pytest.fixture
def mock_container_list() -> list[dict[str, Any]]:
    """Données de test pour les conteneurs LXC."""
    return [
        {
            "vmid": 200,
            "name": "nginx-proxy",
            "status": "running",
            "cpu": 0.02,
            "cpus": 1,
            "mem": 268435456,  # 256 MB
            "maxmem": 536870912,  # 512 MB
            "disk": 1073741824,  # 1 GB
            "maxdisk": 5368709120,  # 5 GB
            "uptime": 259200,
            "netin": 100000,
            "netout": 50000,
        },
        {
            "vmid": 201,
            "name": "redis-cache",
            "status": "running",
            "cpu": 0.01,
            "cpus": 1,
            "mem": 134217728,  # 128 MB
            "maxmem": 268435456,  # 256 MB
            "disk": 536870912,  # 512 MB
            "maxdisk": 2147483648,  # 2 GB
            "uptime": 345600,
            "netin": 200000,
            "netout": 100000,
        },
    ]


@pytest.fixture
def mock_snapshot_list() -> list[dict[str, Any]]:
    """Données de test pour les snapshots."""
    return [
        {
            "name": "current",
            "description": "You are here!",
            "snaptime": None,
            "parent": "before-upgrade",
        },
        {
            "name": "before-upgrade",
            "description": "Snapshot before system upgrade",
            "snaptime": 1704067200,  # 2024-01-01
            "parent": "initial",
            "vmstate": False,
        },
        {
            "name": "initial",
            "description": "Initial installation",
            "snaptime": 1703980800,
            "parent": None,
            "vmstate": True,
        },
    ]


@pytest.fixture
def mock_storage_list() -> list[dict[str, Any]]:
    """Données de test pour les storages."""
    return [
        {
            "storage": "local",
            "type": "dir",
            "content": "iso,vztmpl,backup",
            "active": 1,
            "enabled": 1,
            "shared": 0,
            "used": 53687091200,  # 50 GB
            "avail": 161061273600,  # 150 GB
            "total": 214748364800,  # 200 GB
        },
        {
            "storage": "local-lvm",
            "type": "lvmthin",
            "content": "images,rootdir",
            "active": 1,
            "enabled": 1,
            "shared": 0,
            "used": 214748364800,  # 200 GB
            "avail": 322122547200,  # 300 GB
            "total": 536870912000,  # 500 GB
        },
    ]


@pytest.fixture
def mock_task_list() -> list[dict[str, Any]]:
    """Données de test pour les tâches."""
    return [
        {
            "upid": "UPID:pve1:00001234:00000001:65432100:qmstart:100:root@pam:",
            "node": "pve1",
            "type": "qmstart",
            "status": "OK",
            "user": "root@pam",
            "starttime": 1704067200,
            "endtime": 1704067210,
            "exitstatus": "OK",
            "id": "100",
        },
        {
            "upid": "UPID:pve1:00001235:00000002:65432200:vzdump:101:root@pam:",
            "node": "pve1",
            "type": "vzdump",
            "status": "running",
            "user": "root@pam",
            "starttime": 1704067300,
            "endtime": None,
            "exitstatus": None,
            "id": "101",
        },
    ]
