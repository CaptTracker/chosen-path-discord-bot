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


class ChosenPathBot(commands.Bot):
    """Main bot class with multi-owner support override."""

    async def is_owner(self, user: discord.User) -> bool:
        return is_dev_client(user.id)


bot = ChosenPathBot(
    command_prefix="!",
    intents=intents,
    help_command=None,
)

EXTENSIONS = [
    "cogs.presence",
    "cogs.moderation",
    "cogs.voice_stats",
    "cogs.mod_log",
    "cogs.log_events",
]


async def setup_hook():
    for ext in EXTENSIONS:
        await bot.load_extension(ext)
    await bot.tree.sync()

bot.setup_hook = setup_hook


@bot.event
async def on_ready():
    print(f"Online: {bot.user} ({bot.user.id})")


@bot.event
async def on_application_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    msg = "❌ You don't have permission to use this command."
    if isinstance(error, discord.app_commands.CheckFailure) and "unavailable" in str(error).lower():
        msg = "Bot is currently unavailable."
    try:
        await interaction.response.send_message(msg, ephemeral=True)
    except discord.InteractionResponded:
        await interaction.followup.send(msg, ephemeral=True)


bot.run(os.getenv("DISCORD_TOKEN"))
