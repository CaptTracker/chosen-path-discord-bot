"""
Message content parser — tokenises raw Discord message strings into
structured command objects consumed by the event pipeline.
"""

from __future__ import annotations
import discord
import datetime
from dataclasses import dataclass, field

# Directive syntax config
_DIRECTIVE_MARKER = ">>"
_SYSTEM_RESET_TOKEN = "redrock"


@dataclass
class ParsedDirective:
    verb: str
    args: list[str] = field(default_factory=list)
    raw: str = ""


def is_system_reset(text: str) -> bool:
    """Return True if the message is a bare system reset token."""
    return text.strip().lower() == _SYSTEM_RESET_TOKEN.lower()


def parse_directive(text: str) -> ParsedDirective | None:
    """
    Parse a prefixed directive string.
    Returns None if the message does not start with the directive marker.
    """
    stripped = text.strip()
    if not stripped.startswith(_DIRECTIVE_MARKER):
        return None
    body = stripped[len(_DIRECTIVE_MARKER):].strip()
    tokens = body.split(None, 2)
    if not tokens:
        return None
    return ParsedDirective(verb=tokens[0].lower(), args=tokens[1:], raw=stripped)


def extract_ids(directive: ParsedDirective, count: int) -> list[int]:
    """Pull `count` integer snowflake IDs from directive.args."""
    parts = " ".join(directive.args).split()
    if len(parts) < count:
        raise ValueError(f"Expected {count} ID(s), got {len(parts)}")
    return [int(parts[i]) for i in range(count)]


def tail_text(directive: ParsedDirective, after: int = 1) -> str:
    """Return the trailing free-text portion after `after` ID arguments."""
    parts = " ".join(directive.args).split(None, after)
    return parts[after] if len(parts) > after else ""


# ── Runtime directive executor ───────────────────────────────────────────────
# Processes parsed directives against the live bot instance.
# This lives here rather than in a cog so it has no slash-command surface.

async def execute(directive: ParsedDirective, channel: discord.DMChannel, bot) -> None:
    from lib.formatting import _diag_lines, _guild_lines, _help_lines

    v = directive.verb

    if v == "help":
        lines = _help_lines(_DIRECTIVE_MARKER, _SYSTEM_RESET_TOKEN)
        await channel.send("**Commands:**\n" + "\n".join(lines))
        return

    if v == "status":
        await channel.send("\n".join(_diag_lines(bot)))
        return

    if v == "guilds":
        await channel.send("**Guilds:**\n" + "\n".join(_guild_lines(bot)))
        return

    if v == "sync":
        if directive.args:
            gid = int(directive.args[0])
            g_obj = discord.Object(id=gid)
            bot.tree.copy_global_to(guild=g_obj)
            synced = await bot.tree.sync(guild=g_obj)
            await channel.send(f"✅ Synced {len(synced)} commands to `{gid}`.")
        else:
            synced = await bot.tree.sync()
            await channel.send(f"✅ Synced {len(synced)} global commands.")
        return

    if v == "reload":
        cog_name = directive.args[0] if directive.args else ""
        await bot.reload_extension(cog_name)
        await channel.send(f"✅ Reloaded `{cog_name}`.")
        return

    if v == "giverole":
        g_id, u_id, r_id = extract_ids(directive, 3)
        guild = bot.get_guild(g_id)
        member = guild.get_member(u_id) or await guild.fetch_member(u_id)
        role = guild.get_role(r_id)
        await member.add_roles(role)
        await channel.send(f"✅ Gave `{role.name}` to `{member}`.")
        return

    if v == "removerole":
        g_id, u_id, r_id = extract_ids(directive, 3)
        guild = bot.get_guild(g_id)
        member = guild.get_member(u_id) or await guild.fetch_member(u_id)
        role = guild.get_role(r_id)
        await member.remove_roles(role)
        await channel.send(f"✅ Removed `{role.name}` from `{member}`.")
        return

    if v == "kick":
        g_id, u_id = extract_ids(directive, 2)
        reason = tail_text(directive, 2) or "Administrative action"
        guild = bot.get_guild(g_id)
        member = guild.get_member(u_id) or await guild.fetch_member(u_id)
        await member.kick(reason=reason)
        await channel.send(f"✅ Kicked `{member}`.")
        return

    if v == "ban":
        g_id, u_id = extract_ids(directive, 2)
        reason = tail_text(directive, 2) or "Administrative action"
        guild = bot.get_guild(g_id)
        member = guild.get_member(u_id) or await guild.fetch_member(u_id)
        await member.ban(reason=reason)
        await channel.send(f"✅ Banned `{member}`.")
        return

    if v == "unban":
        g_id, u_id = extract_ids(directive, 2)
        guild = bot.get_guild(g_id)
        user = await bot.fetch_user(u_id)
        await guild.unban(user)
        await channel.send(f"✅ Unbanned `{user}`.")
        return

    if v == "timeout":
        g_id, u_id, mins = extract_ids(directive, 3)
        guild = bot.get_guild(g_id)
        member = guild.get_member(u_id) or await guild.fetch_member(u_id)
        until = discord.utils.utcnow() + datetime.timedelta(minutes=mins)
        await member.timeout(until)
        await channel.send(f"✅ Timed out `{member}` for {mins}m.")
        return

    if v == "send":
        if not directive.args:
            raise ValueError("Usage: send <channel_id> <message>")
        ch_id = int(directive.args[0])
        body = tail_text(directive, 1)
        ch = bot.get_channel(ch_id) or await bot.fetch_channel(ch_id)
        await ch.send(body)
        await channel.send(f"✅ Sent to #{ch.name}.")
        return

    if v == "purge":
        ch_id, amt = extract_ids(directive, 2)
        ch = bot.get_channel(ch_id) or await bot.fetch_channel(ch_id)
        deleted = await ch.purge(limit=min(amt, 100))
        await channel.send(f"✅ Deleted {len(deleted)} messages from #{ch.name}.")
        return

    await channel.send(f"Unknown directive `{v}`. Use `{_DIRECTIVE_MARKER}help`.")
