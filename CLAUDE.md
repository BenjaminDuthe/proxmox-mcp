# CLAUDE.md - MCP Proxmox

## REGLE ABSOLUE : Wiki-First

**AVANT de lire du code source, TOUJOURS consulter le Wiki (7 pages) :**

```
wikijs_get_page(path="MCP-Proxmox")                            # Index + sommaire
wikijs_get_page(path="MCP-Proxmox/<page>")                     # Page specifique
wikijs_search_pages(query="MCP-Proxmox <sujet>")               # Recherche
```

**INTERDIT** : Glob/Grep/Read pour "explorer" l'architecture. Utiliser UNIQUEMENT pour les fichiers a modifier.

---

## REGLE ABSOLUE : Vaultwarden comme coffre-fort unique

**Tous les secrets (mots de passe, tokens, API keys) sont centralises dans Vaultwarden** (organisation `SiteCraft`, `https://vault.sitecraft-it.com`).

- **JAMAIS de secrets en clair** dans CLAUDE.md, MEMORY.md ou le code
- **Avant chaque tache necessitant un secret** : le recuperer depuis Vaultwarden
- **Apres chaque creation/modification de secret** : mettre a jour l'item Vaultwarden dans la collection du projet
- **Les .env restent le mecanisme d'execution** — Vaultwarden est la source de verite

---

## Project Overview

MCP (Model Context Protocol) server enabling Claude to interact with Proxmox VE infrastructure for VM, LXC container, and cluster resource management.

## Tech Stack Requirements

- **Python 3.11+**
- **MCP SDK**: Official `mcp` package (NOT FastMCP)
- **HTTP Client**: `httpx` (async) - custom client, NOT proxmoxer
- **Validation**: `pydantic` v2
- **Packaging**: `pyproject.toml` only (no setup.py, no requirements.txt)

## Common Commands

```bash
# Install in development mode
pip install -e ".[dev]"

# Run the MCP server
python -m proxmox_mcp.server

# Run tests
pytest -v --cov=proxmox_mcp

# Run a single test file
pytest tests/test_tools/test_vms.py -v

# Lint and format
ruff check src/
ruff format src/
```

## Architecture

### Core Components

- `src/proxmox_mcp/server.py` - MCP server entry point, tool registration using `@server.list_tools()` and `@server.call_tool()` decorators
- `src/proxmox_mcp/client.py` - Async Proxmox API client with dual auth support (token API or user/password with auto-renewal)
- `src/proxmox_mcp/config.py` - Environment-based configuration via pydantic
- `src/proxmox_mcp/models.py` - Pydantic models for API inputs/outputs
- `src/proxmox_mcp/tools/` - Tool implementations organized by domain (nodes, vms, containers, snapshots, storage, tasks, ssh, users)
  - `set_vm_config` - Modify QEMU VM configuration (CPU, RAM, name, etc.) via PUT /nodes/{node}/qemu/{vmid}/config
  - `set_container_config` - Modify LXC container configuration (CPU, RAM, swap, hostname, etc.) via PUT /nodes/{node}/lxc/{vmid}/config
- `src/proxmox_mcp/ssh_client.py` - Async SSH client using asyncssh for direct node access

### Authentication Flow

1. Token API (preferred): `Authorization: PVEAPIToken={tokenid}={secret}`
2. User/password fallback: POST to `/access/ticket` for ticket + CSRFPreventionToken (2h validity, auto-renew)

### Proxmox API Base URL

`https://{host}:{port}/api2/json`

## Response Format Convention

All tools must return this structure:

```python
# Success with list
{"success": True, "count": N, "data": [...]}

# Success with single object
{"success": True, "data": {...}}

# Success with action
{"success": True, "message": "...", "task_id": "UPID:...", "vmid": N, "node": "..."}

# Error
{"success": False, "error": "...", "error_code": "VM_NOT_FOUND"}
```

Error codes: `AUTH_FAILED`, `CONNECTION_ERROR`, `NODE_NOT_FOUND`, `VM_NOT_FOUND`, `SNAPSHOT_NOT_FOUND`, `STORAGE_NOT_FOUND`, `PERMISSION_DENIED`, `TASK_FAILED`, `INVALID_STATE`, `API_ERROR`, `USER_NOT_FOUND`, `INVALID_FORMAT`, `PASSWORD_REQUIRED`, `NO_CHANGES`, `SSH_AUTH_FAILED`, `SSH_CONNECTION_ERROR`, `SSH_COMMAND_FAILED`, `SSH_FILE_NOT_FOUND`, `SSH_TIMEOUT`

## Code Conventions

- All functions must have type hints for parameters and return values
- Use `str | None` union syntax (not `Optional[str]`)
- Google-style docstrings with Args, Returns, Raises sections
- Async throughout (`async def`, `await`)
- VM type parameter uses `Literal["qemu", "lxc"]`

## Environment Variables

Required for connection:
- `PROXMOX_HOST` - IP or hostname (no https://, no port)
- `PROXMOX_PORT` - Default 8006

Authentication (token preferred):
- `PROXMOX_TOKEN_ID` - Format: `user@pam!token-name`
- `PROXMOX_TOKEN_SECRET` - UUID format

Or user/password:
- `PROXMOX_USER` - Format: `root@pam`
- `PROXMOX_PASSWORD`

Options:
- `PROXMOX_VERIFY_SSL` - Default false (self-signed certs)
- `PROXMOX_TIMEOUT` - Default 30 seconds

## SSH Access

Direct SSH access to Proxmox nodes enables system-level administration tasks that the Proxmox API doesn't expose.

### SSH Tools

- `ssh_execute` - Execute shell commands on a node
- `ssh_read_file` - Read remote file content
- `ssh_write_file` - Write files with automatic backup
- `fix_apt_repos` - Helper to configure Proxmox community repositories (disable enterprise, enable no-subscription)

### SSH Environment Variables

SSH is automatically enabled when authentication is configured:

- `PROXMOX_SSH_KEY_PATH` - Path to SSH private key (recommended, e.g., `~/.ssh/id_rsa`)
- `PROXMOX_SSH_PASSWORD` - SSH password (fallback if no key)
- `PROXMOX_SSH_USER` - SSH username (default: `root`)
- `PROXMOX_SSH_PORT` - SSH port (default: `22`)
- `PROXMOX_SSH_TIMEOUT` - Connection timeout in seconds (default: `30`)

### SSH Response Format

```python
# Command execution
{
    "success": True,
    "data": {
        "command": "hostname",
        "exit_code": 0,
        "stdout": "pve1\n",
        "stderr": "",
        "duration_ms": 45
    }
}

# File read
{
    "success": True,
    "data": {
        "path": "/etc/apt/sources.list",
        "exists": True,
        "size": 1234,
        "content": "..."
    }
}

# File write (with backup)
{
    "success": True,
    "message": "Fichier écrit avec succès",
    "data": {
        "path": "/etc/apt/sources.list.d/pve.list",
        "backup_path": "/etc/apt/sources.list.d/pve.list.bak.20240115_143022",
        "size": 89
    }
}
```
