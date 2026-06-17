import discord
from discord import app_commands
from discord.ext import commands, tasks
import aiosqlite
import datetime
from .checks import admin_check

DB_PATH = "bot_data.db"

# How long (seconds) to wait between stat channel updates to avoid rate-limits
UPDATE_INTERVAL = 300  # 5 minutes (Discord rate-limits channel edits heavily)


class VoiceStats(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        bot.loop.create_task(self._init_db())
        self.update_stat_channels.start()

    def cog_unload(self):
        self.update_stat_channels.cancel()

    async def _init_db(self):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS stat_channels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    stat_type TEXT NOT NULL,
                    template TEXT NOT NULL
                )
            """)
            await db.commit()

    async def get_stat_channels(self, guild_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT channel_id, stat_type, template FROM stat_channels WHERE guild_id = ?",
                (guild_id,),
            ) as cur:
                return await cur.fetchall()

    def _format_template(self, template: str, guild: discord.Guild) -> str:
        total = guild.member_count or 0
        humans = sum(1 for m in guild.members if not m.bot)
        bots = sum(1 for m in guild.members if m.bot)
        online = sum(1 for m in guild.members if m.status != discord.Status.offline and not m.bot)
        return (
            template
            .replace("{total}", str(total))
            .replace("{humans}", str(humans))
            .replace("{bots}", str(bots))
            .replace("{online}", str(online))
        )

    @tasks.loop(seconds=UPDATE_INTERVAL)
    async def update_stat_channels(self):
        for guild in self.bot.guilds:
            rows = await self.get_stat_channels(guild.id)
            for channel_id, stat_type, template in rows:
                channel = guild.get_channel(channel_id)
                if not channel:
                    continue
                new_name = self._format_template(template, guild)
                if channel.name != new_name:
                    try:
                        await channel.edit(name=new_name, reason="Stat channel update")
                    except discord.Forbidden:
                        pass
                    except discord.HTTPException:
                        pass

    @update_stat_channels.before_loop
    async def before_update(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        await self._trigger_update(member.guild)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        await self._trigger_update(member.guild)

    async def _trigger_update(self, guild: discord.Guild):
        """Update stat channels immediately on join/leave (still subject to Discord rate-limits)."""
        rows = await self.get_stat_channels(guild.id)
        for channel_id, stat_type, template in rows:
            channel = guild.get_channel(channel_id)
            if not channel:
                continue
            new_name = self._format_template(template, guild)
            if channel.name != new_name:
                try:
                    await channel.edit(name=new_name, reason="Stat channel update")
                except (discord.Forbidden, discord.HTTPException):
                    pass

    # ── Admin commands ───────────────────────────────────────────────────

    stat_group = app_commands.Group(name="stats", description="Manage stat voice channels")

    @stat_group.command(name="add", description="Add a stat voice channel")
    @app_commands.describe(
        channel="The voice channel to use as a stat display",
        template="Template string. Variables: {total} {humans} {bots} {online}",
    )
    @admin_check()
    async def stats_add(self, interaction: discord.Interaction, channel: discord.VoiceChannel, template: str):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO stat_channels (guild_id, channel_id, stat_type, template) VALUES (?, ?, ?, ?)",
                (interaction.guild.id, channel.id, "custom", template),
            )
            await db.commit()
        preview = self._format_template(template, interaction.guild)
        await interaction.response.send_message(
            f"✅ Stat channel added.\nChannel: {channel.mention}\nTemplate: `{template}`\nPreview: `{preview}`"
        )
        await self._trigger_update(interaction.guild)

    @stat_group.command(name="remove", description="Remove a stat voice channel")
    @app_commands.describe(channel="The voice channel to stop using as a stat display")
    @admin_check()
    async def stats_remove(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "DELETE FROM stat_channels WHERE guild_id = ? AND channel_id = ?",
                (interaction.guild.id, channel.id),
            )
            await db.commit()
        await interaction.response.send_message(f"✅ Removed stat tracking from {channel.mention}.")

    @stat_group.command(name="list", description="List all stat voice channels in this server")
    async def stats_list(self, interaction: discord.Interaction):
        rows = await self.get_stat_channels(interaction.guild.id)
        if not rows:
            await interaction.response.send_message("No stat channels configured. Use `/stats add` to set one up.", ephemeral=True)
            return
        lines = []
        for channel_id, stat_type, template in rows:
            ch = interaction.guild.get_channel(channel_id)
            name = ch.mention if ch else f"(deleted channel {channel_id})"
            lines.append(f"{name} — `{template}`")
        embed = discord.Embed(title="🦕 Stat Channels", description="\n".join(lines), color=discord.Color.blurple())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @stat_group.command(name="presets", description="Show available template variable presets")
    async def stats_presets(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🦕 Stat Channel Template Variables",
            color=discord.Color.blurple(),
            description=(
                "Use these in your template when running `/stats add`:\n\n"
                "`{total}` — Total member count\n"
                "`{humans}` — Non-bot members\n"
                "`{bots}` — Bot accounts\n"
                "`{online}` — Online (non-offline) members\n\n"
                "**Example templates:**\n"
                "`Members: {total}`\n"
                "`🦕 Players: {humans}`\n"
                "`👥 Total: {total} | 🟢 Online: {online}`"
            ),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    cog = VoiceStats(bot)
    bot.add_cog(cog)
    bot.tree.add_command(cog.stat_group)
