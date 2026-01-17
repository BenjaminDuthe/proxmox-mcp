"""Tools pour la gestion des utilisateurs Proxmox."""

from typing import Any

from proxmox_mcp.client import ProxmoxClient
from proxmox_mcp.exceptions import ProxmoxError


async def list_users(client: ProxmoxClient) -> dict[str, Any]:
    """Liste tous les utilisateurs Proxmox.

    Args:
        client: Client Proxmox

    Returns:
        Liste des utilisateurs avec leurs informations
    """
    try:
        response = await client.get("/access/users")
        data = response.get("data", [])

        users = []
        for user in data:
            users.append({
                "userid": user.get("userid"),
                "email": user.get("email"),
                "firstname": user.get("firstname"),
                "lastname": user.get("lastname"),
                "comment": user.get("comment"),
                "enable": user.get("enable", 1) == 1,
                "expire": user.get("expire", 0),
                "groups": user.get("groups", ""),
                "realm": user.get("userid", "@").split("@")[-1] if user.get("userid") else "",
            })

        return {
            "success": True,
            "count": len(users),
            "data": users,
        }

    except ProxmoxError as e:
        return e.to_dict()


async def get_user(client: ProxmoxClient, userid: str) -> dict[str, Any]:
    """Récupère les détails d'un utilisateur Proxmox.

    Args:
        client: Client Proxmox
        userid: ID de l'utilisateur (format: user@realm)

    Returns:
        Détails de l'utilisateur
    """
    try:
        response = await client.get(f"/access/users/{userid}")
        data = response.get("data")

        if data is None:
            return {
                "success": False,
                "error": f"Utilisateur '{userid}' introuvable",
                "error_code": "USER_NOT_FOUND",
            }

        return {
            "success": True,
            "data": {
                "userid": userid,
                "email": data.get("email"),
                "firstname": data.get("firstname"),
                "lastname": data.get("lastname"),
                "comment": data.get("comment"),
                "enable": data.get("enable", 1) == 1,
                "expire": data.get("expire", 0),
                "groups": data.get("groups", []),
                "tokens": data.get("tokens", []),
            },
        }

    except ProxmoxError as e:
        return e.to_dict()


async def create_user(
    client: ProxmoxClient,
    userid: str,
    password: str | None = None,
    email: str | None = None,
    firstname: str | None = None,
    lastname: str | None = None,
    comment: str | None = None,
    groups: str | None = None,
    expire: int = 0,
    enable: bool = True,
) -> dict[str, Any]:
    """Crée un nouvel utilisateur Proxmox.

    Args:
        client: Client Proxmox
        userid: ID de l'utilisateur (format: user@realm, ex: admin@pve ou user@pam)
        password: Mot de passe (requis pour realm pve, optionnel pour pam)
        email: Adresse email
        firstname: Prénom
        lastname: Nom
        comment: Commentaire/description
        groups: Groupes (séparés par des virgules)
        expire: Timestamp d'expiration (0 = jamais)
        enable: Activer l'utilisateur

    Returns:
        Résultat de la création
    """
    try:
        # Valider le format userid
        if "@" not in userid:
            return {
                "success": False,
                "error": "Format userid invalide. Utilisez user@realm (ex: admin@pve, root@pam)",
                "error_code": "INVALID_FORMAT",
            }

        realm = userid.split("@")[-1]

        # Le mot de passe est requis pour le realm pve
        if realm == "pve" and not password:
            return {
                "success": False,
                "error": "Le mot de passe est requis pour les utilisateurs du realm 'pve'",
                "error_code": "PASSWORD_REQUIRED",
            }

        # Construire les données
        data: dict[str, Any] = {
            "userid": userid,
            "enable": 1 if enable else 0,
            "expire": expire,
        }

        if password:
            data["password"] = password
        if email:
            data["email"] = email
        if firstname:
            data["firstname"] = firstname
        if lastname:
            data["lastname"] = lastname
        if comment:
            data["comment"] = comment
        if groups:
            data["groups"] = groups

        await client.post("/access/users", data)

        return {
            "success": True,
            "message": f"Utilisateur '{userid}' créé avec succès",
            "data": {
                "userid": userid,
                "realm": realm,
                "enable": enable,
            },
        }

    except ProxmoxError as e:
        return e.to_dict()


async def update_user(
    client: ProxmoxClient,
    userid: str,
    password: str | None = None,
    email: str | None = None,
    firstname: str | None = None,
    lastname: str | None = None,
    comment: str | None = None,
    groups: str | None = None,
    expire: int | None = None,
    enable: bool | None = None,
) -> dict[str, Any]:
    """Modifie un utilisateur Proxmox existant.

    Args:
        client: Client Proxmox
        userid: ID de l'utilisateur (format: user@realm)
        password: Nouveau mot de passe
        email: Nouvelle adresse email
        firstname: Nouveau prénom
        lastname: Nouveau nom
        comment: Nouveau commentaire
        groups: Nouveaux groupes (séparés par des virgules)
        expire: Nouveau timestamp d'expiration
        enable: Activer/désactiver l'utilisateur

    Returns:
        Résultat de la modification
    """
    try:
        # Construire les données (seulement les champs fournis)
        data: dict[str, Any] = {}

        if password is not None:
            data["password"] = password
        if email is not None:
            data["email"] = email
        if firstname is not None:
            data["firstname"] = firstname
        if lastname is not None:
            data["lastname"] = lastname
        if comment is not None:
            data["comment"] = comment
        if groups is not None:
            data["groups"] = groups
        if expire is not None:
            data["expire"] = expire
        if enable is not None:
            data["enable"] = 1 if enable else 0

        if not data:
            return {
                "success": False,
                "error": "Aucune modification spécifiée",
                "error_code": "NO_CHANGES",
            }

        await client.put(f"/access/users/{userid}", data)

        return {
            "success": True,
            "message": f"Utilisateur '{userid}' modifié avec succès",
            "data": {
                "userid": userid,
                "changes": list(data.keys()),
            },
        }

    except ProxmoxError as e:
        return e.to_dict()


async def delete_user(client: ProxmoxClient, userid: str) -> dict[str, Any]:
    """Supprime un utilisateur Proxmox.

    Args:
        client: Client Proxmox
        userid: ID de l'utilisateur (format: user@realm)

    Returns:
        Résultat de la suppression
    """
    try:
        # Empêcher la suppression de root@pam
        if userid == "root@pam":
            return {
                "success": False,
                "error": "Impossible de supprimer l'utilisateur root@pam",
                "error_code": "PERMISSION_DENIED",
            }

        await client.delete(f"/access/users/{userid}")

        return {
            "success": True,
            "message": f"Utilisateur '{userid}' supprimé avec succès",
            "data": {
                "userid": userid,
            },
        }

    except ProxmoxError as e:
        return e.to_dict()
