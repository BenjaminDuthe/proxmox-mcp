# Proxmox MCP Server

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/MCP-Compatible-green.svg)](https://modelcontextprotocol.io/)

A Model Context Protocol (MCP) server that enables Claude to manage Proxmox VE infrastructure — VMs, LXC containers, snapshots, storage, and more.

## Features

- **Node Management** — List cluster nodes, monitor CPU/RAM/disk metrics
- **VM & Container Control** — Start, stop, reboot, destroy QEMU VMs and LXC containers
- **Snapshots** — Create, list, delete, and rollback snapshots
- **Storage** — Browse storage pools and content (ISOs, backups, templates)
- **Task Monitoring** — Track Proxmox tasks in real-time
- **SSH Access** — Execute commands directly on Proxmox host
- **User Management** — Create, update, delete Proxmox users
- **Guest Agent** — Execute commands inside VMs via QEMU Guest Agent
- **Docker Ready** — Run as a container with minimal configuration

---

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/BenjaminDuthe/proxmox-mcp.git
cd proxmox-mcp
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your Proxmox credentials:

```env
PROXMOX_HOST=192.168.1.10
PROXMOX_TOKEN_ID=root@pam!mcp
PROXMOX_TOKEN_SECRET=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
PROXMOX_VERIFY_SSL=false
```

### 3. Run with Docker (recommended)

```bash
docker compose up -d
```

Or install locally:

```bash
pip install -e .
python -m proxmox_mcp.server
```

---

## Installation

### Prerequisites

- Python 3.11+ (local install) or Docker
- Proxmox VE 7.x or 8.x with API access
- API Token with appropriate permissions

### Local Installation

```bash
# Install package
pip install -e ".[dev]"

# Run server
python -m proxmox_mcp.server
```

### Docker Installation

```bash
# Build image
docker build -t proxmox-mcp .

# Run with environment file
docker run --rm -it --env-file .env proxmox-mcp
```

For SSH support, mount your SSH key:

```bash
docker run --rm -it \
  --env-file .env \
  -e PROXMOX_SSH_KEY_PATH=/home/mcp/.ssh/id_rsa \
  -v ~/.ssh/id_proxmox:/home/mcp/.ssh/id_rsa:ro \
  proxmox-mcp
```

---

## Configuration

### Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `PROXMOX_HOST` | Proxmox server IP or hostname | Yes | — |
| `PROXMOX_PORT` | API port | No | `8006` |
| `PROXMOX_TOKEN_ID` | API token ID (`user@realm!token`) | Yes* | — |
| `PROXMOX_TOKEN_SECRET` | API token secret | Yes* | — |
| `PROXMOX_USER` | Username (alternative to token) | Yes* | — |
| `PROXMOX_PASSWORD` | Password (alternative to token) | Yes* | — |
| `PROXMOX_VERIFY_SSL` | Verify SSL certificate | No | `false` |
| `PROXMOX_TIMEOUT` | Request timeout (seconds) | No | `30` |
| `PROXMOX_SSH_KEY_PATH` | Path to SSH private key | No | — |
| `PROXMOX_SSH_USER` | SSH username | No | `root` |

*Either token OR user/password required. Token is recommended.

### Creating an API Token in Proxmox

1. Go to **Datacenter** → **Permissions** → **API Tokens**
2. Click **Add**
3. Select user, enter token name (e.g., `mcp`)
4. **Uncheck** "Privilege Separation" to inherit user permissions
5. Copy the token secret (shown only once)

### Claude Desktop Configuration

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "proxmox": {
      "command": "python",
      "args": ["-m", "proxmox_mcp.server"],
      "cwd": "/path/to/proxmox-mcp",
      "env": {
        "PROXMOX_HOST": "192.168.1.10",
        "PROXMOX_TOKEN_ID": "root@pam!mcp",
        "PROXMOX_TOKEN_SECRET": "your-token-secret",
        "PROXMOX_VERIFY_SSL": "false"
      }
    }
  }
}
```

With Docker:

```json
{
  "mcpServers": {
    "proxmox": {
      "command": "docker",
      "args": ["run", "--rm", "-i", "--env-file", "/path/to/.env", "proxmox-mcp"]
    }
  }
}
```

---

## Available Tools

### Nodes

| Tool | Description |
|------|-------------|
| `list_nodes` | List all cluster nodes with CPU/RAM/disk metrics |
| `get_node_status` | Get detailed status of a specific node |

### Virtual Machines (QEMU)

| Tool | Description |
|------|-------------|
| `list_vms` | List all VMs with status and resource usage |
| `get_vm_details` | Get full VM configuration |
| `start_vm` | Start a VM |
| `stop_vm` | Force stop a VM |
| `shutdown_vm` | Graceful shutdown (ACPI) |
| `reboot_vm` | Reboot a VM |
| `destroy_vm` | **Permanently delete** a VM and its disks |

### Containers (LXC)

| Tool | Description |
|------|-------------|
| `list_containers` | List all LXC containers |
| `get_container_details` | Get full container configuration |

*LXC containers support the same start/stop/shutdown/reboot/destroy operations as VMs.*

### Snapshots

| Tool | Description |
|------|-------------|
| `list_snapshots` | List snapshots of a VM/container |
| `create_snapshot` | Create a new snapshot |
| `delete_snapshot` | Delete a snapshot |
| `rollback_snapshot` | Restore VM/container to a snapshot |

### Storage

| Tool | Description |
|------|-------------|
| `list_storage` | List storage pools with usage stats |
| `get_storage_content` | List content (ISOs, backups, images) |

### Tasks

| Tool | Description |
|------|-------------|
| `list_tasks` | List recent Proxmox tasks |
| `get_task_status` | Get detailed task status by UPID |

### SSH (Proxmox Host)

| Tool | Description |
|------|-------------|
| `ssh_execute` | Execute command on Proxmox host |
| `ssh_read_file` | Read file from Proxmox host |
| `ssh_write_file` | Write file to Proxmox host |
| `fix_apt_repos` | Fix APT repos for non-subscription |

### Users

| Tool | Description |
|------|-------------|
| `list_users` | List all Proxmox users |
| `get_user` | Get user details and tokens |
| `create_user` | Create a new user |
| `update_user` | Update user properties |
| `delete_user` | Delete a user |

### Guest Agent (VM)

| Tool | Description |
|------|-------------|
| `vm_exec` | Execute command inside VM |
| `vm_exec_status` | Get async command result |
| `vm_exec_sync` | Execute command and wait for result |
| `vm_file_read` | Read file from inside VM |
| `vm_file_write` | Write file inside VM (protected paths) |

---

## Architecture

```
src/proxmox_mcp/
├── server.py          # MCP server entry point
├── client.py          # Async Proxmox API client (httpx)
├── ssh_client.py      # Async SSH client (asyncssh)
├── config.py          # Environment-based configuration
├── models.py          # Pydantic models
├── exceptions.py      # Custom exceptions
└── tools/             # Tool implementations
    ├── nodes.py
    ├── vms.py
    ├── containers.py
    ├── snapshots.py
    ├── storage.py
    ├── tasks.py
    ├── ssh.py
    └── users.py
```

---

## Development

### Install dev dependencies

```bash
pip install -e ".[dev]"
```

### Run tests

```bash
pytest -v --cov=proxmox_mcp
```

### Lint and format

```bash
ruff check src/
ruff format src/
```

---

## Security Notes

- **Never commit `.env`** — It contains sensitive credentials
- **Use API tokens** — Prefer tokens over user/password
- **Limit token permissions** — Create dedicated tokens with minimal required permissions
- **Protected paths** — `vm_file_write` blocks writes to sensitive files (`/etc/shadow`, `/etc/passwd`, etc.)

---

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

---

## Acknowledgments

- [Proxmox VE](https://www.proxmox.com/) — Powerful open-source virtualization platform
- [Model Context Protocol](https://modelcontextprotocol.io/) — Anthropic's protocol for AI tool integration
- [Claude](https://claude.ai/) — AI assistant by Anthropic
