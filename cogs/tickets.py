import discord
from discord import app_commands
from discord.ext import commands
import aiosqlite
import datetime
import io
import os
from .checks import mod_check, admin_check

DB_PATH = os.getenv("DB_PATH", "bot_data.db")

CATEGORIES = [
    discord.SelectOption(label="General Support",   value="general", emoji="🦕", description="General questions and help"),
    discord.SelectOption(label="Player Report",     value="report",  emoji="📋", description="Report a player for rule violations"),
    discord.SelectOption(label="Ban Appeal",        value="appeal",  emoji="⚖️",  description="Appeal a ban or punishment"),
    discord.SelectOption(label="Bug Report",        value="bug",     emoji="🐛", description="Report a bug or technical issue"),
    discord.SelectOption(label="Staff Application", value="staff",   emoji="🌟", description="Apply for a staff position"),
    discord.SelectOption(label="Other",             value="other",   emoji="❓", description="Anything else"),
]

CATEGORY_NAMES = {
    "general": "🦕 General Support",
    "report":  "📋 Player Report",
    "appeal":  "⚖️ Ban Appeal",
    "bug":     "🐛 Bug Report",
    "staff":   "🌟 Staff Application",
    "other":   "❓ Other",
}


# ── Database helpers ─────────────────────────────────────────────────────────

async def _init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id       INTEGER NOT NULL,
                channel_id     INTEGER NOT NULL,
                user_id        INTEGER NOT NULL,
                category       TEXT NOT NULL,
                status         TEXT DEFAULT 'open',
                created_at     TEXT NOT NULL,
                ticket_number  INTEGER NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ticket_panels (
                guild_id    INTEGER PRIMARY KEY,
                channel_id  INTEGER NOT NULL,
                message_id  INTEGER NOT NULL
            )
        """)
        await db.commit()


async def _next_number(guild_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT MAX(ticket_number) FROM tickets WHERE guild_id = ?", (guild_id,)
        ) as cur:
            row = await cur.fetchone()
    return (row[0] or 0) + 1


async def _save_ticket(guild_id, channel_id, user_id, category, number):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO tickets (guild_id, channel_id, user_id, category, status, created_at, ticket_number) "
            "VALUES (?, ?, ?, ?, 'open', ?, ?)",
            (guild_id, channel_id, user_id, category,
             datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"), number),
        )
        await db.commit()


async def _get_ticket(channel_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT * FROM tickets WHERE channel_id = ? AND status = 'open'", (channel_id,)
        ) as cur:
            return await cur.fetchone()


async def _close_ticket_db(channel_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE tickets SET status='closed' WHERE channel_id=?", (channel_id,))
        await db.commit()


async def _has_open_ticket(guild_id: int, user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id FROM tickets WHERE guild_id=? AND user_id=? AND status='open'",
            (guild_id, user_id),
        ) as cur:
            return await cur.fetchone() is not None


# ── Helpers ──────────────────────────────────────────────────────────────────

def _role_ids() -> set[int]:
    ids: set[int] = set()
    for key in ("MOD_ROLE_IDS", "ADMIN_ROLE_IDS"):
        raw = os.getenv(key, "")
        ids |= {int(x.strip()) for x in raw.split(",") if x.strip().isdigit()}
    return ids


def _transcript_channel(guild: discord.Guild) -> discord.TextChannel | None:
    return discord.utils.get(guild.text_channels, name="ticket-transcripts")


async def _make_channel(guild: discord.Guild, user: discord.Member, category: str, number: int) -> discord.TextChannel:
    safe_name = user.display_name[:20].lower().replace(" ", "-")
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        guild.me: discord.PermissionOverwrite(
            view_channel=True, send_messages=True,
            manage_channels=True, manage_messages=True,
        ),
        user: discord.PermissionOverwrite(
            view_channel=True, send_messages=True,
            attach_files=True, embed_links=True,
        ),
    }
    for rid in _role_ids():
        role = guild.get_role(rid)
        if role:
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True,
                attach_files=True, manage_messages=True,
            )
    ticket_cat = discord.utils.get(guild.categories, name="Tickets")
    return await guild.create_text_channel(
        name=f"ticket-{number:04d}-{safe_name}",
        overwrites=overwrites,
        category=ticket_cat,
        topic=f"Ticket #{number:04d} | {CATEGORY_NAMES.get(category, category)} | {user}",
    )


async def _generate_transcript(channel: discord.TextChannel, row) -> discord.File:
    _, guild_id, channel_id, user_id, category, status, created_at, number = row
    lines = [
        "=" * 60,
        "TICKET TRANSCRIPT",
        f"Ticket:   #{number:04d}",
        f"Category: {CATEGORY_NAMES.get(category, category)}",
        f"User ID:  {user_id}",
        f"Channel:  #{channel.name}",
        f"Opened:   {created_at}",
        f"Closed:   {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}",
        "=" * 60,
        "",
    ]
    async for msg in channel.history(limit=500, oldest_first=True):
        if msg.author.bot and not msg.content:
            continue
        ts = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
        lines.append(f"[{ts}] {msg.author.display_name} ({msg.author})")
        if msg.content:
            lines.append(f"  {msg.content}")
        for a in msg.attachments:
            lines.append(f"  [Attachment: {a.filename}] {a.url}")
        if msg.embeds:
            for e in msg.embeds:
                if e.title:
                    lines.append(f"  [Embed: {e.title}]")
        lines.append("")
    return discord.File(
        io.BytesIO("\n".join(lines).encode("utf-8")),
        filename=f"ticket-{number:04d}.txt",
    )


async def _do_close(interaction: discord.Interaction, row):
    _, guild_id, channel_id, user_id, category, status, created_at, number = row
    channel = interaction.channel
    guild   = interaction.guild

    transcript_file = await _generate_transcript(channel, row)
    log_ch = _transcript_channel(guild)

    if log_ch:
        embed = discord.Embed(
            title=f"📋 Ticket Transcript #{number:04d}",
            color=discord.Color.dark_blue(),
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.add_field(name="Category",  value=CATEGORY_NAMES.get(category, category), inline=True)
        embed.add_field(name="Opened by", value=f"<@{user_id}> (`{user_id}`)", inline=True)
        embed.add_field(name="Closed by", value=interaction.user.mention, inline=True)
        embed.add_field(name="Opened at", value=created_at, inline=True)
        await log_ch.send(embed=embed, file=transcript_file)

    await _close_ticket_db(channel_id)

    close_embed = discord.Embed(
        title="🔒 Ticket Closed",
        description=f"Closed by {interaction.user.mention}. Channel deleting in 5 seconds.",
        color=discord.Color.red(),
        timestamp=datetime.datetime.now(datetime.timezone.utc),
    )
    await channel.send(embed=close_embed)
    await interaction.followup.send("✅ Ticket closed.", ephemeral=True)
    await discord.utils.sleep_until(
        datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=5)
    )
    try:
        await channel.delete(reason=f"Ticket #{number:04d} closed")
    except discord.NotFound:
        pass


# ── Persistent views ─────────────────────────────────────────────────────────

class TicketOpenView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Open a Ticket",
        style=discord.ButtonStyle.green,
        custom_id="ticket:open",
        emoji="🎫",
    )
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await _has_open_ticket(interaction.guild.id, interaction.user.id):
            await interaction.response.send_message(
                "❌ You already have an open ticket. Please use your existing ticket channel.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            "Select a category for your ticket:",
            view=CategoryView(),
            ephemeral=True,
        )


class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Close Ticket",
        style=discord.ButtonStyle.red,
        custom_id="ticket:close",
        emoji="🔒",
    )
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        row = await _get_ticket(interaction.channel.id)
        if not row:
            await interaction.response.send_message("❌ This is not an active ticket channel.", ephemeral=True)
            return
        await interaction.response.send_message(
            "Are you sure you want to close this ticket?",
            view=ConfirmCloseView(row),
            ephemeral=True,
        )


# ── Ephemeral views (timeout is fine) ────────────────────────────────────────

class CategorySelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="Choose a ticket category...",
            min_values=1,
            max_values=1,
            options=CATEGORIES,
        )

    async def callback(self, interaction: discord.Interaction):
        category = self.values[0]
        await interaction.response.defer(ephemeral=True)

        if await _has_open_ticket(interaction.guild.id, interaction.user.id):
            await interaction.followup.send("❌ You already have an open ticket.", ephemeral=True)
            return

        number  = await _next_number(interaction.guild.id)
        channel = await _make_channel(interaction.guild, interaction.user, category, number)
        await _save_ticket(interaction.guild.id, channel.id, interaction.user.id, category, number)

        cat_name = CATEGORY_NAMES.get(category, category)
        embed = discord.Embed(
            title=f"🎫 Ticket #{number:04d} — {cat_name}",
            description=(
                f"Welcome, {interaction.user.mention}! A staff member will be with you shortly.\n\n"
                "Please describe your issue in as much detail as possible."
            ),
            color=discord.Color.blurple(),
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.add_field(name="Category",  value=cat_name,                 inline=True)
        embed.add_field(name="Opened by", value=interaction.user.mention, inline=True)
        embed.set_footer(text="Click Close Ticket when your issue is resolved.")
        await channel.send(content=interaction.user.mention, embed=embed, view=TicketControlView())
        await interaction.followup.send(f"✅ Ticket created: {channel.mention}", ephemeral=True)


class CategoryView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(CategorySelect())


class ConfirmCloseView(discord.ui.View):
    def __init__(self, row):
        super().__init__(timeout=60)
        self.row = row

    @discord.ui.button(label="Confirm Close", style=discord.ButtonStyle.red, emoji="🔒")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        await _do_close(interaction, self.row)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Cancelled.", ephemeral=True)
        self.stop()


# ── Cog ───────────────────────────────────────────────────────────────────────

class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        bot.add_view(TicketOpenView())
        bot.add_view(TicketControlView())
        bot.loop.create_task(_init_db())

    @app_commands.command(name="ticketpanel", description="Post the ticket panel in a channel")
    @app_commands.describe(channel="Channel to post the panel in")
    @admin_check()
    async def ticket_panel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        embed = discord.Embed(
            title="🦕 Support Tickets",
            description=(
                "Need help from our staff? Open a ticket below.\n\n"
                "🦕 **General Support** — General questions and help\n"
                "📋 **Player Report** — Report a player for rule violations\n"
                "⚖️ **Ban Appeal** — Appeal a ban or punishment\n"
                "🐛 **Bug Report** — Report a bug or technical issue\n"
                "🌟 **Staff Application** — Apply for a staff position\n"
                "❓ **Other** — Anything else\n\n"
                "Click the button below to get started."
            ),
            color=discord.Color.green(),
        )
        embed.set_footer(text="Chosen Path | Path of Titans")
        msg = await channel.send(embed=embed, view=TicketOpenView())

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR REPLACE INTO ticket_panels (guild_id, channel_id, message_id) VALUES (?, ?, ?)",
                (interaction.guild.id, channel.id, msg.id),
            )
            await db.commit()

        await interaction.response.send_message(f"✅ Ticket panel posted in {channel.mention}.", ephemeral=True)

    @app_commands.command(name="ticket", description="Open a ticket for a user")
    @app_commands.describe(user="Member to open a ticket for", category="Ticket category")
    @app_commands.choices(category=[
        app_commands.Choice(name="🦕 General Support",   value="general"),
        app_commands.Choice(name="📋 Player Report",     value="report"),
        app_commands.Choice(name="⚖️ Ban Appeal",         value="appeal"),
        app_commands.Choice(name="🐛 Bug Report",         value="bug"),
        app_commands.Choice(name="🌟 Staff Application",  value="staff"),
        app_commands.Choice(name="❓ Other",              value="other"),
    ])
    @mod_check()
    async def create_ticket(self, interaction: discord.Interaction, user: discord.Member, category: str = "general"):
        await interaction.response.defer(ephemeral=True)

        if await _has_open_ticket(interaction.guild.id, user.id):
            await interaction.followup.send(f"❌ {user.mention} already has an open ticket.", ephemeral=True)
            return

        number  = await _next_number(interaction.guild.id)
        channel = await _make_channel(interaction.guild, user, category, number)
        await _save_ticket(interaction.guild.id, channel.id, user.id, category, number)

        cat_name = CATEGORY_NAMES.get(category, category)
        embed = discord.Embed(
            title=f"🎫 Ticket #{number:04d} — {cat_name}",
            description=(
                f"Welcome, {user.mention}! A staff member will be with you shortly.\n\n"
                f"This ticket was opened by {interaction.user.mention}."
            ),
            color=discord.Color.blurple(),
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.add_field(name="Category",  value=cat_name,            inline=True)
        embed.add_field(name="User",      value=user.mention,        inline=True)
        embed.add_field(name="Opened by", value=interaction.user.mention, inline=True)
        embed.set_footer(text="Click Close Ticket when resolved.")
        await channel.send(content=user.mention, embed=embed, view=TicketControlView())
        await interaction.followup.send(f"✅ Ticket created: {channel.mention}", ephemeral=True)

    @app_commands.command(name="addtoticket", description="Add a user to the current ticket")
    @app_commands.describe(user="User to add")
    @mod_check()
    async def add_to_ticket(self, interaction: discord.Interaction, user: discord.Member):
        if not await _get_ticket(interaction.channel.id):
            await interaction.response.send_message("❌ This is not an active ticket channel.", ephemeral=True)
            return
        await interaction.channel.set_permissions(
            user, view_channel=True, send_messages=True,
            attach_files=True, embed_links=True,
        )
        await interaction.response.send_message(f"✅ Added {user.mention} to this ticket.")

    @app_commands.command(name="closeticket", description="Close the current ticket")
    @mod_check()
    async def close_ticket_cmd(self, interaction: discord.Interaction):
        row = await _get_ticket(interaction.channel.id)
        if not row:
            await interaction.response.send_message("❌ This is not an active ticket channel.", ephemeral=True)
            return
        await interaction.response.send_message("Close this ticket?", view=ConfirmCloseView(row), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
