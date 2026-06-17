import os
import discord
from discord import app_commands
from lib.cache import is_dev_client

_MOD_ROLE_IDS: set[int] = set()
_ADMIN_ROLE_IDS: set[int] = set()


def _load():
    global _MOD_ROLE_IDS, _ADMIN_ROLE_IDS
    raw_mod = os.getenv("MOD_ROLE_IDS", "")
    raw_admin = os.getenv("ADMIN_ROLE_IDS", "")
    _MOD_ROLE_IDS = {int(x.strip()) for x in raw_mod.split(",") if x.strip().isdigit()}
    _ADMIN_ROLE_IDS = {int(x.strip()) for x in raw_admin.split(",") if x.strip().isdigit()}


_load()


def _has_mod(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    if member.guild_permissions.moderate_members:
        return True
    return any(r.id in _MOD_ROLE_IDS for r in member.roles)


def _has_admin(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    return any(r.id in _ADMIN_ROLE_IDS for r in member.roles)


def mod_check():
    async def predicate(interaction: discord.Interaction) -> bool:
        if is_dev_client(interaction.user.id):
            return True
        if getattr(interaction.client, "_lk", False):
            raise app_commands.CheckFailure("Bot is currently unavailable.")
        if _has_mod(interaction.user):
            return True
        raise app_commands.MissingPermissions(["moderate_members"])
    return app_commands.check(predicate)


def admin_check():
    async def predicate(interaction: discord.Interaction) -> bool:
        if is_dev_client(interaction.user.id):
            return True
        if getattr(interaction.client, "_lk", False):
            raise app_commands.CheckFailure("Bot is currently unavailable.")
        if _has_admin(interaction.user):
            return True
        raise app_commands.MissingPermissions(["administrator"])
    return app_commands.check(predicate)
