import discord
from discord.ext import commands
import datetime
from lib.log_channels import LOG_USER, LOG_CHAT, LOG_SERVER

_LOG_CHANNEL_IDS = {LOG_USER, LOG_CHAT, LOG_SERVER}


def _ts() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _trim(text: str, limit: int = 1024) -> str:
    return text if len(text) <= limit else text[:limit - 3] + "..."


class LogEvents(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _ch(self, guild: discord.Guild, channel_id: int) -> discord.TextChannel | None:
        return guild.get_channel(channel_id)

    # ── User Logs ────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        ch = self._ch(member.guild, LOG_USER)
        if not ch:
            return
        age = discord.utils.utcnow() - member.created_at
        embed = discord.Embed(title="📥 Member Joined", color=discord.Color.green(), timestamp=_ts())
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="User", value=f"{member.mention} (`{member.id}`)", inline=False)
        embed.add_field(name="Account Age", value=f"{age.days} days", inline=True)
        embed.add_field(name="Member Count", value=str(member.guild.member_count), inline=True)
        embed.set_footer(text=str(member))
        await ch.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        ch = self._ch(member.guild, LOG_USER)
        if not ch:
            return
        roles = [r.mention for r in reversed(member.roles) if r != member.guild.default_role]
        joined = discord.utils.format_dt(member.joined_at, "R") if member.joined_at else "Unknown"
        embed = discord.Embed(title="📤 Member Left", color=discord.Color.red(), timestamp=_ts())
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="User", value=f"{member} (`{member.id}`)", inline=False)
        embed.add_field(name="Joined", value=joined, inline=True)
        embed.add_field(name="Member Count", value=str(member.guild.member_count), inline=True)
        if roles:
            embed.add_field(name=f"Roles ({len(roles)})", value=" ".join(roles[:15]), inline=False)
        await ch.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        ch = self._ch(after.guild, LOG_USER)
        if not ch:
            return

        # Nickname change
        if before.nick != after.nick:
            embed = discord.Embed(title="✏️ Nickname Changed", color=discord.Color.blurple(), timestamp=_ts())
            embed.set_thumbnail(url=after.display_avatar.url)
            embed.add_field(name="User", value=f"{after.mention} (`{after.id}`)", inline=False)
            embed.add_field(name="Before", value=before.nick or "*None*", inline=True)
            embed.add_field(name="After", value=after.nick or "*None*", inline=True)
            await ch.send(embed=embed)

        # Role changes
        added = [r for r in after.roles if r not in before.roles]
        removed = [r for r in before.roles if r not in after.roles]
        if added or removed:
            embed = discord.Embed(title="🎭 Roles Updated", color=discord.Color.blurple(), timestamp=_ts())
            embed.set_thumbnail(url=after.display_avatar.url)
            embed.add_field(name="User", value=f"{after.mention} (`{after.id}`)", inline=False)
            if added:
                embed.add_field(name="Added", value=" ".join(r.mention for r in added), inline=True)
            if removed:
                embed.add_field(name="Removed", value=" ".join(r.mention for r in removed), inline=True)
            await ch.send(embed=embed)

        # Timeout applied/removed
        before_to = bool(before.timed_out_until)
        after_to = bool(after.timed_out_until)
        if not before_to and after_to:
            embed = discord.Embed(title="⏱️ Member Timed Out", color=discord.Color.yellow(), timestamp=_ts())
            embed.add_field(name="User", value=f"{after.mention} (`{after.id}`)", inline=False)
            embed.add_field(name="Until", value=discord.utils.format_dt(after.timed_out_until, "F"), inline=True)
            await ch.send(embed=embed)
        elif before_to and not after_to:
            embed = discord.Embed(title="⏱️ Timeout Removed", color=discord.Color.green(), timestamp=_ts())
            embed.add_field(name="User", value=f"{after.mention} (`{after.id}`)", inline=False)
            await ch.send(embed=embed)

    @commands.Cog.listener()
    async def on_user_update(self, before: discord.User, after: discord.User):
        for guild in self.bot.guilds:
            if not guild.get_member(after.id):
                continue
            ch = self._ch(guild, LOG_USER)
            if not ch:
                continue
            if before.name != after.name or before.global_name != after.global_name:
                embed = discord.Embed(title="✏️ Username Changed", color=discord.Color.blurple(), timestamp=_ts())
                embed.set_thumbnail(url=after.display_avatar.url)
                embed.add_field(name="User ID", value=str(after.id), inline=False)
                embed.add_field(name="Before", value=str(before), inline=True)
                embed.add_field(name="After", value=str(after), inline=True)
                await ch.send(embed=embed)
            if before.avatar != after.avatar:
                embed = discord.Embed(title="🖼️ Avatar Changed", color=discord.Color.blurple(), timestamp=_ts())
                embed.add_field(name="User", value=f"{after} (`{after.id}`)", inline=False)
                embed.set_thumbnail(url=after.display_avatar.url)
                if before.avatar:
                    embed.set_image(url=before.display_avatar.url)
                await ch.send(embed=embed)

    # ── Chat Logs ────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.author.bot:
            return
        if before.content == after.content:
            return
        if not before.guild:
            return
        if before.channel.id in _LOG_CHANNEL_IDS:
            return
        ch = self._ch(before.guild, LOG_CHAT)
        if not ch:
            return
        embed = discord.Embed(title="✏️ Message Edited", color=discord.Color.gold(), timestamp=_ts())
        embed.add_field(name="Author", value=f"{before.author.mention} (`{before.author.id}`)", inline=True)
        embed.add_field(name="Channel", value=before.channel.mention, inline=True)
        embed.add_field(name="Before", value=_trim(before.content or "*No text content*"), inline=False)
        embed.add_field(name="After", value=_trim(after.content or "*No text content*"), inline=False)
        embed.add_field(name="Jump", value=f"[Go to message]({after.jump_url})", inline=False)
        embed.set_footer(text=f"Message ID: {before.id}")
        await ch.send(embed=embed)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.bot:
            return
        if not message.guild:
            return
        if message.channel.id in _LOG_CHANNEL_IDS:
            return
        ch = self._ch(message.guild, LOG_CHAT)
        if not ch:
            return
        embed = discord.Embed(title="🗑️ Message Deleted", color=discord.Color.red(), timestamp=_ts())
        embed.add_field(name="Author", value=f"{message.author.mention} (`{message.author.id}`)", inline=True)
        embed.add_field(name="Channel", value=message.channel.mention, inline=True)
        if message.content:
            embed.add_field(name="Content", value=_trim(message.content), inline=False)
        if message.attachments:
            embed.add_field(name="Attachments", value="\n".join(a.filename for a in message.attachments), inline=False)
        embed.set_footer(text=f"Message ID: {message.id}")
        await ch.send(embed=embed)

    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages: list[discord.Message]):
        if not messages:
            return
        guild = messages[0].guild
        if not guild:
            return
        ch = self._ch(guild, LOG_CHAT)
        if not ch:
            return
        channels = {m.channel.mention for m in messages}
        embed = discord.Embed(title="🗑️ Bulk Delete", color=discord.Color.dark_red(), timestamp=_ts())
        embed.add_field(name="Messages Deleted", value=str(len(messages)), inline=True)
        embed.add_field(name="Channel(s)", value=", ".join(channels), inline=True)
        await ch.send(embed=embed)

    # ── Server Logs ──────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        ch = self._ch(channel.guild, LOG_SERVER)
        if not ch:
            return
        embed = discord.Embed(title="➕ Channel Created", color=discord.Color.green(), timestamp=_ts())
        embed.add_field(name="Name", value=channel.mention, inline=True)
        embed.add_field(name="Type", value=str(channel.type).replace("_", " ").title(), inline=True)
        embed.add_field(name="ID", value=str(channel.id), inline=True)
        if hasattr(channel, "category") and channel.category:
            embed.add_field(name="Category", value=channel.category.name, inline=True)
        await ch.send(embed=embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        ch = self._ch(channel.guild, LOG_SERVER)
        if not ch:
            return
        embed = discord.Embed(title="➖ Channel Deleted", color=discord.Color.red(), timestamp=_ts())
        embed.add_field(name="Name", value=f"#{channel.name}", inline=True)
        embed.add_field(name="Type", value=str(channel.type).replace("_", " ").title(), inline=True)
        embed.add_field(name="ID", value=str(channel.id), inline=True)
        await ch.send(embed=embed)

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
        ch = self._ch(after.guild, LOG_SERVER)
        if not ch:
            return
        changes = []
        if before.name != after.name:
            changes.append(f"**Name:** `{before.name}` → `{after.name}`")
        if hasattr(before, "topic") and before.topic != after.topic:
            changes.append(f"**Topic:** `{before.topic or 'None'}` → `{after.topic or 'None'}`")
        if hasattr(before, "slowmode_delay") and before.slowmode_delay != after.slowmode_delay:
            changes.append(f"**Slowmode:** `{before.slowmode_delay}s` → `{after.slowmode_delay}s`")
        if hasattr(before, "nsfw") and before.nsfw != after.nsfw:
            changes.append(f"**NSFW:** `{before.nsfw}` → `{after.nsfw}`")
        if not changes:
            return
        embed = discord.Embed(title="✏️ Channel Updated", color=discord.Color.blurple(), timestamp=_ts())
        embed.add_field(name="Channel", value=after.mention, inline=False)
        embed.add_field(name="Changes", value="\n".join(changes), inline=False)
        await ch.send(embed=embed)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        ch = self._ch(role.guild, LOG_SERVER)
        if not ch:
            return
        embed = discord.Embed(title="➕ Role Created", color=role.color or discord.Color.green(), timestamp=_ts())
        embed.add_field(name="Name", value=role.mention, inline=True)
        embed.add_field(name="ID", value=str(role.id), inline=True)
        embed.add_field(name="Hoisted", value=str(role.hoist), inline=True)
        embed.add_field(name="Mentionable", value=str(role.mentionable), inline=True)
        await ch.send(embed=embed)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        ch = self._ch(role.guild, LOG_SERVER)
        if not ch:
            return
        embed = discord.Embed(title="➖ Role Deleted", color=discord.Color.red(), timestamp=_ts())
        embed.add_field(name="Name", value=f"@{role.name}", inline=True)
        embed.add_field(name="ID", value=str(role.id), inline=True)
        await ch.send(embed=embed)

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        ch = self._ch(after.guild, LOG_SERVER)
        if not ch:
            return
        changes = []
        if before.name != after.name:
            changes.append(f"**Name:** `{before.name}` → `{after.name}`")
        if before.color != after.color:
            changes.append(f"**Color:** `{before.color}` → `{after.color}`")
        if before.hoist != after.hoist:
            changes.append(f"**Hoisted:** `{before.hoist}` → `{after.hoist}`")
        if before.mentionable != after.mentionable:
            changes.append(f"**Mentionable:** `{before.mentionable}` → `{after.mentionable}`")
        if before.permissions != after.permissions:
            changes.append("**Permissions changed**")
        if not changes:
            return
        embed = discord.Embed(title="✏️ Role Updated", color=after.color or discord.Color.blurple(), timestamp=_ts())
        embed.add_field(name="Role", value=after.mention, inline=False)
        embed.add_field(name="Changes", value="\n".join(changes), inline=False)
        await ch.send(embed=embed)

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild):
        ch = self._ch(after, LOG_SERVER)
        if not ch:
            return
        changes = []
        if before.name != after.name:
            changes.append(f"**Name:** `{before.name}` → `{after.name}`")
        if before.icon != after.icon:
            changes.append("**Icon changed**")
        if before.verification_level != after.verification_level:
            changes.append(f"**Verification Level:** `{before.verification_level}` → `{after.verification_level}`")
        if before.explicit_content_filter != after.explicit_content_filter:
            changes.append(f"**Content Filter:** `{before.explicit_content_filter}` → `{after.explicit_content_filter}`")
        if before.default_notifications != after.default_notifications:
            changes.append(f"**Notifications:** `{before.default_notifications}` → `{after.default_notifications}`")
        if not changes:
            return
        embed = discord.Embed(title="⚙️ Server Updated", color=discord.Color.blurple(), timestamp=_ts())
        embed.add_field(name="Changes", value="\n".join(changes), inline=False)
        if after.icon:
            embed.set_thumbnail(url=after.icon.url)
        await ch.send(embed=embed)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot:
            return
        ch = self._ch(member.guild, LOG_SERVER)
        if not ch:
            return

        if before.channel is None and after.channel is not None:
            embed = discord.Embed(title="🔊 Joined Voice", color=discord.Color.green(), timestamp=_ts())
            embed.add_field(name="Member", value=f"{member.mention} (`{member.id}`)", inline=True)
            embed.add_field(name="Channel", value=after.channel.name, inline=True)
            await ch.send(embed=embed)

        elif before.channel is not None and after.channel is None:
            embed = discord.Embed(title="🔇 Left Voice", color=discord.Color.red(), timestamp=_ts())
            embed.add_field(name="Member", value=f"{member.mention} (`{member.id}`)", inline=True)
            embed.add_field(name="Channel", value=before.channel.name, inline=True)
            await ch.send(embed=embed)

        elif before.channel != after.channel:
            embed = discord.Embed(title="🔀 Moved Voice Channel", color=discord.Color.blurple(), timestamp=_ts())
            embed.add_field(name="Member", value=f"{member.mention} (`{member.id}`)", inline=False)
            embed.add_field(name="From", value=before.channel.name, inline=True)
            embed.add_field(name="To", value=after.channel.name, inline=True)
            await ch.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(LogEvents(bot))
