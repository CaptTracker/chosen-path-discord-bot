import discord
from discord import app_commands
from discord.ext import commands
import aiosqlite
import datetime
import io
import os
from .checks import mod_check, admin_check

DB_PATH = os.getenv("DB_PATH", "bot_data.db")

# Each top-level type maps to (display name, emoji, Discord server category name, description)
TICKET_TYPES = {
    "discord":     ("Discord Ticket",  "💬", "Discord Tickets",  "Server issues, user reports, role requests, general Discord help"),
    "game":        ("Game Ticket",     "🎮", "Game Tickets",      "In-game issues, bug reports, game support, tribe help"),
    "appeal":      ("Appeal",          "⚖️",  "Appeal Tickets",   "Appeal a ban, mute, timeout, or other punishment"),
    "application": ("Application",     "📋", "Applications",      "Apply for staff, moderator, or other server roles"),
}

# Slash command choices list built from TICKET_TYPES
_TICKET_CHOICES = [
    app_commands.Choice(name=f"{data[1]} {data[0]}", value=key)
    for key, data in TICKET_TYPES.items()
]


# ── Database ─────────────────────────────────────────────────────────────────

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


# ── Helpers ───────────────────────────────────────────────────────────────────

def _role_ids() -> set[int]:
    ids: set[int] = set()
    for key in ("MOD_ROLE_IDS", "ADMIN_ROLE_IDS"):
        raw = os.getenv(key, "")
        ids |= {int(x.strip()) for x in raw.split(",") if x.strip().isdigit()}
    return ids


def _transcript_channel(guild: discord.Guild) -> discord.TextChannel | None:
    return discord.utils.get(guild.text_channels, name="ticket-transcripts")


def _display(ticket_type: str) -> str:
    data = TICKET_TYPES.get(ticket_type)
    return f"{data[1]} {data[0]}" if data else ticket_type


def _server_category_name(ticket_type: str) -> str:
    data = TICKET_TYPES.get(ticket_type)
    return data[2] if data else "Tickets"


async def _get_or_create_category(guild: discord.Guild, name: str) -> discord.CategoryChannel:
    cat = discord.utils.get(guild.categories, name=name)
    if cat:
        return cat
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        guild.me: discord.PermissionOverwrite(view_channel=True, manage_channels=True),
    }
    for rid in _role_ids():
        role = guild.get_role(rid)
        if role:
            overwrites[role] = discord.PermissionOverwrite(view_channel=True)
    return await guild.create_category(name=name, overwrites=overwrites)


async def _make_channel(guild: discord.Guild, user: discord.Member, ticket_type: str, number: int) -> discord.TextChannel:
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
    cat = await _get_or_create_category(guild, _server_category_name(ticket_type))
    return await guild.create_text_channel(
        name=f"ticket-{number:04d}-{safe_name}",
        overwrites=overwrites,
        category=cat,
        topic=f"Ticket #{number:04d} | {_display(ticket_type)} | {user}",
    )


async def _generate_transcript(channel: discord.TextChannel, row) -> discord.File:
    _, guild_id, channel_id, user_id, category, status, created_at, number = row
    lines = [
        "=" * 60,
        "TICKET TRANSCRIPT",
        f"Ticket:   #{number:04d}",
        f"Type:     {_display(category)}",
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
        embed.add_field(name="Type",      value=_display(category),            inline=True)
        embed.add_field(name="Opened by", value=f"<@{user_id}> (`{user_id}`)", inline=True)
        embed.add_field(name="Closed by", value=interaction.user.mention,      inline=True)
        embed.add_field(name="Opened at", value=created_at,                    inline=True)
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


# ── Ticket open panel — 4 buttons, one per type ───────────────────────────────

async def _open_ticket_for(interaction: discord.Interaction, ticket_type: str):
    if await _has_open_ticket(interaction.guild.id, interaction.user.id):
        await interaction.response.send_message(
            "❌ You already have an open ticket. Please use your existing ticket channel.",
            ephemeral=True,
        )
        return
    await interaction.response.defer(ephemeral=True)
    number  = await _next_number(interaction.guild.id)
    channel = await _make_channel(interaction.guild, interaction.user, ticket_type, number)
    await _save_ticket(interaction.guild.id, channel.id, interaction.user.id, ticket_type, number)

    display = _display(ticket_type)
    desc_map = {
        "discord":     "Please describe your Discord-related issue and a staff member will assist you shortly.",
        "game":        "Please describe your in-game issue in detail. Include your in-game name if relevant.",
        "appeal":      "Please state what you were punished for, why you believe it was unjust, and any relevant context.",
        "application": "Please introduce yourself, your experience, and why you'd like to join the team.",
    }
    embed = discord.Embed(
        title=f"🎫 Ticket #{number:04d} — {display}",
        description=f"Welcome, {interaction.user.mention}!\n\n{desc_map.get(ticket_type, 'A staff member will be with you shortly.')}",
        color=discord.Color.blurple(),
        timestamp=datetime.datetime.now(datetime.timezone.utc),
    )
    embed.add_field(name="Type",      value=display,                    inline=True)
    embed.add_field(name="Opened by", value=interaction.user.mention,   inline=True)
    embed.set_footer(text="Click Close Ticket when your issue is resolved.")
    await channel.send(content=interaction.user.mention, embed=embed, view=TicketControlView())
    await interaction.followup.send(f"✅ Ticket created: {channel.mention}", ephemeral=True)


class TicketOpenView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Discord Ticket", style=discord.ButtonStyle.blurple, custom_id="ticket:discord", emoji="💬")
    async def open_discord(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _open_ticket_for(interaction, "discord")

    @discord.ui.button(label="Game Ticket", style=discord.ButtonStyle.green, custom_id="ticket:game", emoji="🎮")
    async def open_game(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _open_ticket_for(interaction, "game")

    @discord.ui.button(label="Appeal", style=discord.ButtonStyle.red, custom_id="ticket:appeal", emoji="⚖️")
    async def open_appeal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _open_ticket_for(interaction, "appeal")

    @discord.ui.button(label="Application", style=discord.ButtonStyle.gray, custom_id="ticket:application", emoji="📋")
    async def open_application(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _open_ticket_for(interaction, "application")


class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.red, custom_id="ticket:close", emoji="🔒")
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
            title="🦕 Open a Support Ticket",
            description=(
                "Select the type of ticket that best matches your needs.\n\n"
                "💬 **Discord Ticket** — Server issues, user reports, role requests, general Discord help\n"
                "🎮 **Game Ticket** — In-game issues, bug reports, game support, tribe help\n"
                "⚖️ **Appeal** — Appeal a ban, mute, timeout, or other punishment\n"
                "📋 **Application** — Apply for staff, moderator, or other server roles\n\n"
                "A staff member will respond as soon as possible."
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
    @app_commands.describe(user="Member to open a ticket for", category="Ticket type")
    @app_commands.choices(category=_TICKET_CHOICES)
    @mod_check()
    async def create_ticket(self, interaction: discord.Interaction, user: discord.Member, category: str = "discord"):
        await interaction.response.defer(ephemeral=True)

        if await _has_open_ticket(interaction.guild.id, user.id):
            await interaction.followup.send(f"❌ {user.mention} already has an open ticket.", ephemeral=True)
            return

        number  = await _next_number(interaction.guild.id)
        channel = await _make_channel(interaction.guild, user, category, number)
        await _save_ticket(interaction.guild.id, channel.id, user.id, category, number)

        display = _display(category)
        embed = discord.Embed(
            title=f"🎫 Ticket #{number:04d} — {display}",
            description=(
                f"Welcome, {user.mention}! A staff member will be with you shortly.\n\n"
                f"Opened by {interaction.user.mention}."
            ),
            color=discord.Color.blurple(),
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.add_field(name="Type",      value=display,                    inline=True)
        embed.add_field(name="User",      value=user.mention,               inline=True)
        embed.add_field(name="Opened by", value=interaction.user.mention,   inline=True)
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
