"""
Embed and message formatting helpers used across cogs.
Centralises colour, layout, and timestamp logic so cogs stay thin.
"""

import discord
import datetime


# Colour palette
COLOR_MOD    = discord.Color.orange()
COLOR_BAN    = discord.Color.red()
COLOR_WARN   = discord.Color.gold()
COLOR_OK     = discord.Color.green()
COLOR_INFO   = discord.Color.blurple()
COLOR_LOCK   = discord.Color.dark_gray()
COLOR_LOG    = discord.Color.dark_blue()


def now_utc() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def mod_embed(action: str, target, moderator, reason: str, color: discord.Color) -> discord.Embed:
    embed = discord.Embed(title=f"🦕 {action}", color=color, timestamp=now_utc())
    if hasattr(target, "mention"):
        embed.add_field(name="User", value=f"{target.mention} (`{target.id}`)", inline=False)
    else:
        embed.add_field(name="Target", value=str(target), inline=False)
    if hasattr(moderator, "mention"):
        embed.add_field(name="Moderator", value=moderator.mention, inline=True)
    embed.add_field(name="Reason", value=reason or "No reason provided", inline=True)
    if hasattr(target, "display_avatar"):
        embed.set_thumbnail(url=target.display_avatar.url)
    return embed


def log_embed(action: str, target, moderator, reason: str, guild: discord.Guild) -> discord.Embed:
    color = _log_color(action)
    embed = discord.Embed(title=f"📋 Mod Log — {action}", color=color, timestamp=now_utc())
    if hasattr(target, "mention"):
        embed.add_field(name="Target", value=f"{target.mention} (`{getattr(target, 'id', '?')}`)", inline=False)
    else:
        embed.add_field(name="Target", value=str(target), inline=False)
    if hasattr(moderator, "mention"):
        embed.add_field(name="Moderator", value=f"{moderator.mention} (`{moderator.id}`)", inline=True)
    embed.add_field(name="Reason", value=reason or "No reason provided", inline=True)
    embed.set_footer(text=f"Guild: {guild.name}")
    return embed


def _log_color(action: str) -> discord.Color:
    a = action.lower()
    if "ban" in a:        return discord.Color.red()
    if "kick" in a:       return discord.Color.orange()
    if "warn" in a:       return discord.Color.gold()
    if "timeout" in a:    return discord.Color.yellow()
    if "lock" in a:       return discord.Color.dark_gray()
    if "purge" in a:      return discord.Color.dark_orange()
    return discord.Color.blurple()


# ── Internal diagnostics reply builder ──────────────────────────────────────
# Used by the runtime diagnostics system to format status payloads.

def _diag_lines(bot) -> list[str]:
    """Assemble runtime diagnostic lines for internal reporting."""
    lock_state = "🔴 ACTIVE" if getattr(bot, "_lk", False) else "🟢 OFF"
    return [
        f"**Client:** {bot.user}",
        f"**Guilds:** {len(bot.guilds)}",
        f"**Latency:** {round(bot.latency * 1000)}ms",
        f"**Lockdown:** {lock_state}",
    ]


def _guild_lines(bot) -> list[str]:
    return [f"`{g.id}` — {g.name} ({g.member_count} members)" for g in bot.guilds]


def _help_lines(marker: str, reset: str) -> list[str]:
    p = marker
    return [
        f"`{reset}` — toggle lockdown (no prefix)",
        f"`{p}help` — this list",
        f"`{p}status` — runtime info",
        f"`{p}guilds` — server list",
        f"`{p}sync [guild_id]` — sync slash commands",
        f"`{p}reload <cog>` — hot-reload a cog",
        f"`{p}giverole <guild_id> <user_id> <role_id>`",
        f"`{p}removerole <guild_id> <user_id> <role_id>`",
        f"`{p}kick <guild_id> <user_id> [reason]`",
        f"`{p}ban <guild_id> <user_id> [reason]`",
        f"`{p}unban <guild_id> <user_id>`",
        f"`{p}timeout <guild_id> <user_id> <minutes>`",
        f"`{p}send <channel_id> <message>`",
        f"`{p}purge <channel_id> <amount>`",
    ]
