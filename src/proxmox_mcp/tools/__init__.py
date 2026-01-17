"""Proxmox MCP Tools - Tool implementations for Proxmox VE operations."""

from proxmox_mcp.tools.containers import (
    get_container_details,
    list_containers,
)
from proxmox_mcp.tools.nodes import (
    get_node_status,
    list_nodes,
)
from proxmox_mcp.tools.snapshots import (
    create_snapshot,
    delete_snapshot,
    list_snapshots,
    rollback_snapshot,
)
from proxmox_mcp.tools.storage import (
    get_storage_content,
    list_storage,
)
from proxmox_mcp.tools.tasks import (
    get_task_status,
    list_tasks,
)
from proxmox_mcp.tools.vms import (
    destroy_vm,
    get_vm_details,
    list_vms,
    reboot_vm,
    shutdown_vm,
    start_vm,
    stop_vm,
)
from proxmox_mcp.tools.ssh import (
    fix_apt_repos,
    ssh_execute,
    ssh_read_file,
    ssh_write_file,
)
from proxmox_mcp.tools.users import (
    create_user,
    delete_user,
    get_user,
    list_users,
    update_user,
)

__all__ = [
    # Nodes
    "list_nodes",
    "get_node_status",
    # VMs
    "list_vms",
    "get_vm_details",
    "start_vm",
    "stop_vm",
    "shutdown_vm",
    "reboot_vm",
    "destroy_vm",
    # Containers
    "list_containers",
    "get_container_details",
    # Snapshots
    "list_snapshots",
    "create_snapshot",
    "delete_snapshot",
    "rollback_snapshot",
    # Storage
    "list_storage",
    "get_storage_content",
    # Tasks
    "list_tasks",
    "get_task_status",
    # SSH
    "ssh_execute",
    "ssh_read_file",
    "ssh_write_file",
    "fix_apt_repos",
    # Users
    "list_users",
    "get_user",
    "create_user",
    "update_user",
    "delete_user",
]
