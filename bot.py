import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
from lib.cache import is_dev_client

load_dotenv()

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.voice_states = True

EXTENSIONS = [
    "cogs.presence",
    "cogs.moderation",
    "cogs.voice_stats",
    "cogs.mod_log",
    "cogs.log_events",
    "cogs.tickets",
]


class ChosenPathBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self._synced = False

    async def is_owner(self, user: discord.User) -> bool:
        return is_dev_client(user.id)

    async def setup_hook(self):
        for ext in EXTENSIONS:
            await self.load_extension(ext)

    async def on_ready(self):
        print(f"Online: {self.user} ({self.user.id})")
        if not self._synced:
            for guild in self.guilds:
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
            self._synced = True
            print(f"Synced commands to {len(self.guilds)} guild(s)")


bot = ChosenPathBot()


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    msg = "❌ You don't have permission to use this command."
    if isinstance(error, discord.app_commands.CheckFailure) and "unavailable" in str(error).lower():
        msg = "Bot is currently unavailable."
    try:
        await interaction.response.send_message(msg, ephemeral=True)
    except discord.InteractionResponded:
        await interaction.followup.send(msg, ephemeral=True)


bot.run(os.getenv("DISCORD_TOKEN"))
