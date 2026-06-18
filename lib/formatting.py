"""
Formatting helpers used by the internal runtime pipeline.
"""


def _diag_lines(bot) -> list[str]:
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
