import discord
from discord import app_commands
from discord.ext import commands
import aiosqlite
import datetime
import os
from .checks import admin_check

DB_PATH = "bot_data.db"


class ModLog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        bot.loop.create_task(self._init_db())

    async def _init_db(self):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS log_channels (
                    guild_id INTEGER PRIMARY KEY,
                    channel_id INTEGER NOT NULL
                )
            """)
            await db.commit()

    async def get_log_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT channel_id FROM log_channels WHERE guild_id = ?", (guild.id,)) as cur:
                row = await cur.fetchone()
        if not row:
            return None
        return guild.get_channel(row[0])

    @commands.Cog.listener("on_mod_action")
    async def log_mod_action(self, guild: discord.Guild, action: str, target, moderator: discord.Member, reason: str):
        channel = await self.get_log_channel(guild)
        if not channel:
            return
        embed = discord.Embed(
            title=f"📋 Mod Log — {action}",
            color=self._action_color(action),
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        if hasattr(target, "mention"):
            embed.add_field(name="Target", value=f"{target.mention} (`{getattr(target, 'id', target)}`)", inline=False)
        else:
            embed.add_field(name="Target", value=str(target), inline=False)
        embed.add_field(name="Moderator", value=f"{moderator.mention} (`{moderator.id}`)", inline=True)
        embed.add_field(name="Reason", value=reason or "No reason provided", inline=True)
        embed.set_footer(text=f"Guild: {guild.name}")
        await channel.send(embed=embed)

    def _action_color(self, action: str) -> discord.Color:
        action_lower = action.lower()
        if "ban" in action_lower:
            return discord.Color.red()
        if "kick" in action_lower:
            return discord.Color.orange()
        if "warn" in action_lower:
            return discord.Color.gold()
        if "timeout" in action_lower and "remove" not in action_lower:
            return discord.Color.yellow()
        if "lock" in action_lower:
            return discord.Color.dark_gray()
        if "purge" in action_lower:
            return discord.Color.dark_orange()
        return discord.Color.blurple()

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        # Log bans that happen outside the bot (e.g. manual bans)
        channel = await self.get_log_channel(guild)
        if not channel:
            return
        await discord.utils.sleep_until(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=1))
        async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.ban):
            if entry.target.id == user.id and entry.user.id == self.bot.user.id:
                return  # Already logged by our command
        embed = discord.Embed(title="📋 Mod Log — External Ban", color=discord.Color.dark_red(), timestamp=datetime.datetime.now(datetime.timezone.utc))
        embed.add_field(name="User", value=f"{user} (`{user.id}`)", inline=False)
        embed.set_footer(text="Banned outside of bot commands")
        await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        channel = await self.get_log_channel(member.guild)
        if not channel:
            return
        async for entry in member.guild.audit_logs(limit=1, action=discord.AuditLogAction.kick):
            if entry.target.id == member.id and entry.user.id == self.bot.user.id:
                return  # Already logged by our command
            if entry.target.id == member.id:
                embed = discord.Embed(title="📋 Mod Log — External Kick", color=discord.Color.dark_orange(), timestamp=datetime.datetime.now(datetime.timezone.utc))
                embed.add_field(name="User", value=f"{member} (`{member.id}`)", inline=False)
                embed.add_field(name="Kicked by", value=str(entry.user), inline=True)
                embed.add_field(name="Reason", value=entry.reason or "No reason provided", inline=True)
                await channel.send(embed=embed)
                return

    # ── Admin commands ──────────────────────────────────────────────────

    @app_commands.command(name="setlogchannel", description="Set the moderation log channel")
    @app_commands.describe(channel="The channel to send mod logs to")
    @admin_check()
    async def set_log_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR REPLACE INTO log_channels (guild_id, channel_id) VALUES (?, ?)",
                (interaction.guild.id, channel.id),
            )
            await db.commit()
        await interaction.response.send_message(f"✅ Mod log channel set to {channel.mention}.")

    @app_commands.command(name="logchannel", description="Show the current mod log channel")
    async def show_log_channel(self, interaction: discord.Interaction):
        channel = await self.get_log_channel(interaction.guild)
        if channel:
            await interaction.response.send_message(f"📋 Current mod log channel: {channel.mention}", ephemeral=True)
        else:
            await interaction.response.send_message("❌ No mod log channel set. Use `/setlogchannel` to configure one.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ModLog(bot))
