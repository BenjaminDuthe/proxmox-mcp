# Proxmox MCP Server

Serveur MCP (Model Context Protocol) permettant à Claude d'interagir avec une infrastructure Proxmox VE pour la gestion de VMs, conteneurs LXC et ressources de cluster.

## Fonctionnalités

- **Gestion des nœuds** : Lister les nœuds du cluster, consulter les métriques (CPU, RAM, disque)
- **Gestion des VMs QEMU** : Lister, démarrer, arrêter, redémarrer, supprimer
- **Gestion des conteneurs LXC** : Mêmes opérations que les VMs
- **Snapshots** : Créer, lister, supprimer, restaurer des snapshots
- **Stockage** : Consulter les pools de stockage et leur contenu
- **Tâches** : Suivre les tâches Proxmox en cours et passées

## Installation

### Prérequis

- Python 3.11+
- Accès à un serveur Proxmox VE avec API activée

### Installation locale

```bash
# Cloner le projet
git clone <repo-url>
cd proxmox-mcp

# Installer en mode développement
pip install -e ".[dev]"

# Copier et configurer les variables d'environnement
cp .env.example .env
# Éditer .env avec vos paramètres Proxmox
```

## Configuration

### Variables d'environnement

| Variable | Description | Obligatoire | Défaut |
|----------|-------------|-------------|--------|
| `PROXMOX_HOST` | IP ou hostname du serveur | Oui | - |
| `PROXMOX_PORT` | Port de l'API | Non | 8006 |
| `PROXMOX_TOKEN_ID` | ID du token API | Oui* | - |
| `PROXMOX_TOKEN_SECRET` | Secret du token | Oui* | - |
| `PROXMOX_USER` | Utilisateur Proxmox | Oui* | - |
| `PROXMOX_PASSWORD` | Mot de passe | Oui* | - |
| `PROXMOX_VERIFY_SSL` | Vérifier le certificat SSL | Non | false |
| `PROXMOX_TIMEOUT` | Timeout en secondes | Non | 30 |

*Soit token (recommandé), soit user/password requis.

### Créer un token API dans Proxmox

1. Connectez-vous à l'interface web Proxmox
2. Allez dans **Datacenter** > **Permissions** > **API Tokens**
3. Cliquez sur **Add**
4. Sélectionnez l'utilisateur, donnez un nom au token
5. **Décochez** "Privilege Separation" pour hériter des droits de l'utilisateur
6. Copiez le token secret (affiché une seule fois)

### Configuration Claude Desktop

Ajoutez dans `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) ou équivalent :

```json
{
  "mcpServers": {
    "proxmox": {
      "command": "python",
      "args": ["-m", "proxmox_mcp.server"],
      "cwd": "/chemin/vers/proxmox-mcp",
      "env": {
        "PROXMOX_HOST": "192.168.1.10",
        "PROXMOX_TOKEN_ID": "root@pam!mcp",
        "PROXMOX_TOKEN_SECRET": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
        "PROXMOX_VERIFY_SSL": "false"
      }
    }
  }
}
```

## Utilisation

### Lancer le serveur manuellement

```bash
python -m proxmox_mcp.server
```

### Tools disponibles

#### Lecture (safe)

| Tool | Description |
|------|-------------|
| `list_nodes` | Liste les nœuds du cluster avec métriques |
| `get_node_status` | Détails d'un nœud spécifique |
| `list_vms` | Liste les VMs QEMU |
| `list_containers` | Liste les conteneurs LXC |
| `get_vm_details` | Configuration complète d'une VM |
| `get_container_details` | Configuration complète d'un conteneur |
| `list_snapshots` | Liste les snapshots d'une VM/LXC |
| `list_storage` | Liste les pools de stockage |
| `get_storage_content` | Contenu d'un storage |
| `list_tasks` | Tâches récentes |
| `get_task_status` | Statut d'une tâche |

#### Actions

| Tool | Description |
|------|-------------|
| `start_vm` | Démarre une VM/LXC |
| `stop_vm` | Arrêt forcé |
| `shutdown_vm` | Arrêt gracieux (ACPI) |
| `reboot_vm` | Redémarrage |
| `create_snapshot` | Créer un snapshot |
| `delete_snapshot` | Supprimer un snapshot |
| `rollback_snapshot` | Restaurer un snapshot |

#### Destructif

| Tool | Description |
|------|-------------|
| `destroy_vm` | Supprime définitivement une VM/LXC |

## Développement

### Lancer les tests

```bash
# Tous les tests
pytest -v

# Avec couverture
pytest -v --cov=proxmox_mcp

# Un fichier spécifique
pytest tests/test_tools/test_vms.py -v
```

### Linting et formatage

```bash
# Vérifier le code
ruff check src/

# Formater le code
ruff format src/
```

## Architecture

```
src/proxmox_mcp/
├── server.py          # Point d'entrée MCP, registration des tools
├── client.py          # Client API Proxmox async (httpx)
├── config.py          # Configuration via variables d'environnement
├── models.py          # Modèles Pydantic pour entrées/sorties
├── exceptions.py      # Exceptions personnalisées
└── tools/             # Implémentation des tools par domaine
    ├── nodes.py
    ├── vms.py
    ├── containers.py
    ├── snapshots.py
    ├── storage.py
    └── tasks.py
```

## Licence

MIT
