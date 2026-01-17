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

## Quick Start with Docker Compose

### Step 1: Clone the repository

```bash
git clone https://github.com/BenjaminDuthe/proxmox-mcp.git
cd proxmox-mcp
```

### Step 2: Create your configuration file

```bash
cp .env.example .env
```

### Step 3: Edit `.env` with your Proxmox credentials

Open `.env` in your editor and replace the placeholder values:

```env
# ⚠️ REQUIRED - Replace these values with your own

PROXMOX_HOST=<YOUR_PROXMOX_IP>           # Example: 192.168.1.10
PROXMOX_PORT=8006                         # Default Proxmox port (usually no change needed)

PROXMOX_TOKEN_ID=<YOUR_TOKEN_ID>          # Example: root@pam!mcp
PROXMOX_TOKEN_SECRET=<YOUR_TOKEN_SECRET>  # Example: a1b2c3d4-e5f6-7890-abcd-ef1234567890

PROXMOX_VERIFY_SSL=false                  # Set to 'true' if you have valid SSL certificates
PROXMOX_TIMEOUT=30

# 📌 OPTIONAL - For SSH access to Proxmox host

PROXMOX_SSH_USER=root
PROXMOX_SSH_KEY_PATH=<PATH_TO_YOUR_SSH_KEY>  # Example: ~/.ssh/id_rsa
```

> **📋 Legend:**
> - `<YOUR_PROXMOX_IP>` → Your Proxmox server IP address (e.g., `192.168.1.10`)
> - `<YOUR_TOKEN_ID>` → API token ID created in Proxmox (e.g., `root@pam!mytoken`)
> - `<YOUR_TOKEN_SECRET>` → The secret shown when creating the token (UUID format)
> - `<PATH_TO_YOUR_SSH_KEY>` → Path to your SSH private key (optional, for SSH tools)

### Step 4: Generate SSH key (optional, for SSH tools)

If you want to use SSH tools (`ssh_execute`, `ssh_read_file`, etc.):

```bash
# Generate a dedicated SSH key
ssh-keygen -t ed25519 -f ~/.ssh/id_proxmox -N "" -C "proxmox-mcp"

# Copy the public key to your Proxmox server
ssh-copy-id -i ~/.ssh/id_proxmox.pub root@<YOUR_PROXMOX_IP>
```

Then update `.env`:
```env
PROXMOX_SSH_KEY_PATH=~/.ssh/id_proxmox
```

### Step 5: Start with Docker Compose

```bash
docker compose up -d
```

**What happens:**
1. Docker builds the `proxmox-mcp` image from the Dockerfile
2. The container starts with your `.env` configuration
3. SSH key is mounted read-only inside the container
4. MCP server is ready to receive commands

### Step 6: Check it's running

```bash
# View logs
docker compose logs

# Expected output:
# proxmox-mcp  | INFO - Configuration loaded: 192.168.1.10:8006
# proxmox-mcp  | INFO - Proxmox client connected
# proxmox-mcp  | INFO - MCP server ready
```

### Step 7: Stop/Restart

```bash
# Stop
docker compose down

# Restart (after .env changes)
docker compose up -d --force-recreate

# Rebuild (after code changes)
docker compose up -d --build
```

---

## Docker Compose File Explained

The `docker-compose.yml` file:

```yaml
services:
  proxmox-mcp:
    build: .                    # Build image from local Dockerfile
    image: proxmox-mcp:latest   # Image name
    container_name: proxmox-mcp # Container name

    stdin_open: true            # Keep STDIN open (required for MCP protocol)
    tty: true                   # Allocate pseudo-TTY

    env_file:
      - .env                    # Load environment variables from .env file

    environment:
      # Override SSH key path for container filesystem
      - PROXMOX_SSH_KEY_PATH=/home/mcp/.ssh/id_proxmox

    volumes:
      # Mount your SSH key inside the container (read-only)
      - ~/.ssh/id_proxmox:/home/mcp/.ssh/id_proxmox:ro

    restart: unless-stopped     # Auto-restart on failure
```

**Key points:**
- `stdin_open` + `tty` are required because MCP uses stdio for communication
- `.env` file is loaded automatically (never committed to git)
- SSH key is mounted at `/home/mcp/.ssh/` (container runs as non-root `mcp` user)
- `:ro` means read-only (security best practice)

---

## Alternative: Run with Docker (without Compose)

```bash
# Build the image
docker build -t proxmox-mcp .

# Run with .env file
docker run --rm -it --env-file .env proxmox-mcp

# Run with SSH key mounted
docker run --rm -it \
  --env-file .env \
  -e PROXMOX_SSH_KEY_PATH=/home/mcp/.ssh/id_proxmox \
  -v ~/.ssh/id_proxmox:/home/mcp/.ssh/id_proxmox:ro \
  proxmox-mcp
```

---

## Alternative: Local Installation (without Docker)

```bash
# Install Python package
pip install -e ".[dev]"

# Run MCP server
python -m proxmox_mcp.server
```

---

## Configuration Reference

### Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `PROXMOX_HOST` | Proxmox server IP or hostname | **Yes** | — |
| `PROXMOX_PORT` | API port | No | `8006` |
| `PROXMOX_TOKEN_ID` | API token ID (`user@realm!token`) | **Yes*** | — |
| `PROXMOX_TOKEN_SECRET` | API token secret (UUID) | **Yes*** | — |
| `PROXMOX_USER` | Username (alternative to token) | **Yes*** | — |
| `PROXMOX_PASSWORD` | Password (alternative to token) | **Yes*** | — |
| `PROXMOX_VERIFY_SSL` | Verify SSL certificate | No | `false` |
| `PROXMOX_TIMEOUT` | Request timeout (seconds) | No | `30` |
| `PROXMOX_SSH_KEY_PATH` | Path to SSH private key | No | — |
| `PROXMOX_SSH_USER` | SSH username | No | `root` |

> **\*** Either `TOKEN_ID` + `TOKEN_SECRET` **OR** `USER` + `PASSWORD` is required. Token is recommended.

### Creating an API Token in Proxmox

1. Open Proxmox web interface (https://your-proxmox:8006)
2. Go to **Datacenter** → **Permissions** → **API Tokens**
3. Click **Add**
4. Fill in:
   - **User**: `root@pam` (or your user)
   - **Token ID**: `mcp` (or any name you want)
   - **Privilege Separation**: ⚠️ **Uncheck this** to inherit user permissions
5. Click **Add**
6. **Copy the token secret immediately** (shown only once!)

Your token ID will be: `root@pam!mcp`

---

## Claude Desktop Configuration

### Option 1: With Docker (recommended)

Add to your Claude Desktop config file:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
**Linux**: `~/.config/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "proxmox": {
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "--env-file", "<PATH_TO_PROJECT>/.env",
        "-e", "PROXMOX_SSH_KEY_PATH=/home/mcp/.ssh/id_proxmox",
        "-v", "<PATH_TO_SSH_KEY>:/home/mcp/.ssh/id_proxmox:ro",
        "proxmox-mcp"
      ]
    }
  }
}
```

> **Replace:**
> - `<PATH_TO_PROJECT>` → Full path to the cloned repository (e.g., `/home/user/proxmox-mcp`)
> - `<PATH_TO_SSH_KEY>` → Full path to your SSH private key (e.g., `/home/user/.ssh/id_proxmox`)

### Option 2: With Python (local install)

```json
{
  "mcpServers": {
    "proxmox": {
      "command": "python",
      "args": ["-m", "proxmox_mcp.server"],
      "cwd": "<PATH_TO_PROJECT>",
      "env": {
        "PROXMOX_HOST": "<YOUR_PROXMOX_IP>",
        "PROXMOX_TOKEN_ID": "<YOUR_TOKEN_ID>",
        "PROXMOX_TOKEN_SECRET": "<YOUR_TOKEN_SECRET>",
        "PROXMOX_VERIFY_SSL": "false"
      }
    }
  }
}
```

> **Replace:**
> - `<PATH_TO_PROJECT>` → Full path to the cloned repository
> - `<YOUR_PROXMOX_IP>` → Your Proxmox server IP
> - `<YOUR_TOKEN_ID>` → Your API token ID (e.g., `root@pam!mcp`)
> - `<YOUR_TOKEN_SECRET>` → Your API token secret

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

## Troubleshooting

### "Connection refused" error

- Check that `PROXMOX_HOST` is correct
- Verify Proxmox API is accessible: `curl -k https://<YOUR_PROXMOX_IP>:8006/api2/json`
- Check firewall rules on Proxmox

### "Authentication failed" error

- Verify `PROXMOX_TOKEN_ID` format: `user@realm!tokenname` (e.g., `root@pam!mcp`)
- Check token secret is correct (no extra spaces)
- Ensure "Privilege Separation" is **unchecked** on the token

### SSH tools not working

- Check SSH key path is correct in `.env`
- Verify key is authorized on Proxmox: `ssh -i ~/.ssh/id_proxmox root@<YOUR_PROXMOX_IP>`
- In Docker, ensure the volume mount path matches `PROXMOX_SSH_KEY_PATH`

### Docker: "permission denied" on SSH key

- Ensure the SSH key file has correct permissions: `chmod 600 ~/.ssh/id_proxmox`
- The container runs as `mcp` user (UID 1000)

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
