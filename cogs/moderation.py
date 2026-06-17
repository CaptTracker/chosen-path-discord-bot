import discord
from discord import app_commands
from discord.ext import commands
import datetime
from .checks import mod_check, admin_check


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _mod_embed(self, action, target, moderator, reason, color):
        embed = discord.Embed(
            title=f"🦕 {action}",
            color=color,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.add_field(name="User", value=f"{target.mention} (`{target.id}`)", inline=False)
        embed.add_field(name="Moderator", value=moderator.mention, inline=True)
        embed.add_field(name="Reason", value=reason or "No reason provided", inline=True)
        embed.set_thumbnail(url=target.display_avatar.url)
        return embed

    def _above(self, actor: discord.Member, target: discord.Member) -> bool:
        return actor.top_role > target.top_role

    @app_commands.command(name="kick", description="Kick a member from the server")
    @app_commands.describe(member="Member to kick", reason="Reason")
    @mod_check()
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        if not self._above(interaction.user, member) and not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message("❌ You cannot kick someone with an equal or higher role.", ephemeral=True)
            return
        try:
            await member.send(f"You were **kicked** from **{interaction.guild.name}**.\nReason: {reason}")
        except discord.Forbidden:
            pass
        await member.kick(reason=f"{interaction.user} — {reason}")
        embed = self._mod_embed("Member Kicked", member, interaction.user, reason, discord.Color.orange())
        await interaction.response.send_message(embed=embed)
        self.bot.dispatch("mod_action", interaction.guild, "Kick", member, interaction.user, reason)

    @app_commands.command(name="ban", description="Ban a member from the server")
    @app_commands.describe(member="Member to ban", reason="Reason", delete_days="Days of messages to delete (0-7)")
    @mod_check()
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided", delete_days: int = 0):
        if not self._above(interaction.user, member) and not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message("❌ You cannot ban someone with an equal or higher role.", ephemeral=True)
            return
        delete_days = max(0, min(7, delete_days))
        try:
            await member.send(f"You were **banned** from **{interaction.guild.name}**.\nReason: {reason}")
        except discord.Forbidden:
            pass
        await member.ban(reason=f"{interaction.user} — {reason}", delete_message_days=delete_days)
        embed = self._mod_embed("Member Banned", member, interaction.user, reason, discord.Color.red())
        await interaction.response.send_message(embed=embed)
        self.bot.dispatch("mod_action", interaction.guild, "Ban", member, interaction.user, reason)

    @app_commands.command(name="unban", description="Unban a user by ID")
    @app_commands.describe(user_id="User ID to unban", reason="Reason")
    @mod_check()
    async def unban(self, interaction: discord.Interaction, user_id: str, reason: str = "No reason provided"):
        try:
            uid = int(user_id)
        except ValueError:
            await interaction.response.send_message("❌ Invalid user ID.", ephemeral=True)
            return
        try:
            user = await self.bot.fetch_user(uid)
            await interaction.guild.unban(user, reason=f"{interaction.user} — {reason}")
            embed = discord.Embed(title="🦕 Member Unbanned", color=discord.Color.green(), timestamp=datetime.datetime.now(datetime.timezone.utc))
            embed.add_field(name="User", value=f"{user} (`{user.id}`)", inline=False)
            embed.add_field(name="Moderator", value=interaction.user.mention, inline=True)
            embed.add_field(name="Reason", value=reason, inline=True)
            await interaction.response.send_message(embed=embed)
            self.bot.dispatch("mod_action", interaction.guild, "Unban", user, interaction.user, reason)
        except discord.NotFound:
            await interaction.response.send_message("❌ That user is not banned.", ephemeral=True)

    @app_commands.command(name="timeout", description="Timeout a member")
    @app_commands.describe(member="Member to timeout", duration="Duration in minutes", reason="Reason")
    @mod_check()
    async def timeout(self, interaction: discord.Interaction, member: discord.Member, duration: int = 10, reason: str = "No reason provided"):
        if not self._above(interaction.user, member) and not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message("❌ You cannot timeout someone with an equal or higher role.", ephemeral=True)
            return
        duration = max(1, min(40320, duration))
        until = discord.utils.utcnow() + datetime.timedelta(minutes=duration)
        await member.timeout(until, reason=f"{interaction.user} — {reason}")
        embed = self._mod_embed(f"Member Timed Out ({duration}m)", member, interaction.user, reason, discord.Color.yellow())
        await interaction.response.send_message(embed=embed)
        self.bot.dispatch("mod_action", interaction.guild, f"Timeout ({duration}m)", member, interaction.user, reason)

    @app_commands.command(name="untimeout", description="Remove a timeout from a member")
    @app_commands.describe(member="Member to untimeout", reason="Reason")
    @mod_check()
    async def untimeout(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        await member.timeout(None, reason=f"{interaction.user} — {reason}")
        embed = self._mod_embed("Timeout Removed", member, interaction.user, reason, discord.Color.green())
        await interaction.response.send_message(embed=embed)
        self.bot.dispatch("mod_action", interaction.guild, "Timeout Removed", member, interaction.user, reason)

    @app_commands.command(name="warn", description="Warn a member")
    @app_commands.describe(member="Member to warn", reason="Reason")
    @mod_check()
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        try:
            await member.send(f"⚠️ You were **warned** in **{interaction.guild.name}**.\nReason: {reason}")
        except discord.Forbidden:
            pass
        embed = self._mod_embed("Member Warned", member, interaction.user, reason, discord.Color.gold())
        await interaction.response.send_message(embed=embed)
        self.bot.dispatch("mod_action", interaction.guild, "Warn", member, interaction.user, reason)

    @app_commands.command(name="purge", description="Delete messages in this channel")
    @app_commands.describe(amount="Number of messages to delete (1-100)")
    @mod_check()
    async def purge(self, interaction: discord.Interaction, amount: int):
        amount = max(1, min(100, amount))
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=amount)
        await interaction.followup.send(f"🗑️ Deleted {len(deleted)} messages.", ephemeral=True)
        self.bot.dispatch("mod_action", interaction.guild, f"Purge ({len(deleted)} msgs)", interaction.channel, interaction.user, interaction.channel.mention)

    @app_commands.command(name="slowmode", description="Set channel slowmode")
    @app_commands.describe(seconds="Delay in seconds (0 to disable, max 21600)")
    @mod_check()
    async def slowmode(self, interaction: discord.Interaction, seconds: int = 0):
        seconds = max(0, min(21600, seconds))
        await interaction.channel.edit(slowmode_delay=seconds)
        await interaction.response.send_message(f"✅ Slowmode {'disabled' if seconds == 0 else f'set to **{seconds}s**'}.")

    @app_commands.command(name="lock", description="Lock a channel")
    @mod_check()
    async def lock(self, interaction: discord.Interaction):
        ow = interaction.channel.overwrites_for(interaction.guild.default_role)
        ow.send_messages = False
        await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=ow)
        await interaction.response.send_message("🔒 Channel locked.")
        self.bot.dispatch("mod_action", interaction.guild, "Channel Lock", interaction.channel, interaction.user, interaction.channel.mention)

    @app_commands.command(name="unlock", description="Unlock a channel")
    @mod_check()
    async def unlock(self, interaction: discord.Interaction):
        ow = interaction.channel.overwrites_for(interaction.guild.default_role)
        ow.send_messages = None
        await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=ow)
        await interaction.response.send_message("🔓 Channel unlocked.")
        self.bot.dispatch("mod_action", interaction.guild, "Channel Unlock", interaction.channel, interaction.user, interaction.channel.mention)

    @app_commands.command(name="userinfo", description="Get info about a member")
    @app_commands.describe(member="Member to look up")
    async def userinfo(self, interaction: discord.Interaction, member: discord.Member = None):
        if getattr(self.bot, "_lockdown", False) and not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message("Bot is currently unavailable.", ephemeral=True)
            return
        member = member or interaction.user
        roles = [r.mention for r in reversed(member.roles) if r != interaction.guild.default_role]
        embed = discord.Embed(title=f"🦕 User Info — {member}", color=member.color, timestamp=datetime.datetime.now(datetime.timezone.utc))
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="ID", value=member.id, inline=True)
        embed.add_field(name="Nickname", value=member.nick or "None", inline=True)
        embed.add_field(name="Account Created", value=discord.utils.format_dt(member.created_at, "R"), inline=True)
        embed.add_field(name="Joined Server", value=discord.utils.format_dt(member.joined_at, "R"), inline=True)
        embed.add_field(name="Timed Out", value=bool(member.timed_out_until), inline=True)
        embed.add_field(name=f"Roles ({len(roles)})", value=" ".join(roles[:10]) or "None", inline=False)
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
