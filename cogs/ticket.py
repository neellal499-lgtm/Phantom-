import io
import sqlite3
import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, List

# Custom Emoji Constants
EMOJI_TICK = "<a:Tick:1536982741537656832>"
EMOJI_CROSS = "<:Cross:1536982744008106055>"
DB_FILE = "tickets.db"


class TicketReasonModal(discord.ui.Modal):
    """Pop-up modal prompting users for initial ticket topic and details."""
    def __init__(self, cog: "TicketCog", category_type: str):
        super().__init__(title=f"Open {category_type.title()} Ticket")
        self.cog = cog
        self.category_type = category_type

        self.subject = discord.ui.TextInput(
            label="Subject / Short Summary",
            placeholder="Briefly state why you are opening this ticket...",
            min_length=3,
            max_length=100,
            required=True
        )
        self.description = discord.ui.TextInput(
            label="Detailed Description",
            style=discord.TextStyle.paragraph,
            placeholder="Provide all relevant details, IDs, or context here...",
            min_length=10,
            max_length=1000,
            required=True
        )
        self.add_item(self.subject)
        self.add_item(self.description)

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.create_ticket_channel(
            interaction=interaction,
            category_type=self.category_type,
            subject=self.subject.value,
            description=self.description.value
        )


class TicketControlView(discord.ui.View):
    """Interactive button controls inside opened ticket channels."""
    def __init__(self, cog: "TicketCog"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Claim Ticket", style=discord.ButtonStyle.success, emoji="🙋", custom_id="ticket_btn_claim")
    async def claim_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        support_role_id = await self.cog.get_support_role(interaction.guild_id)
        if support_role_id:
            support_role = interaction.guild.get_role(support_role_id)
            if support_role and support_role not in interaction.user.roles and not interaction.user.guild_permissions.administrator:
                return await interaction.response.send_message(
                    f"{EMOJI_CROSS} Only members with {support_role.mention} can claim tickets.",
                    ephemeral=True
                )

        button.disabled = True
        button.label = f"Claimed by {interaction.user.name}"
        await interaction.message.edit(view=self)

        embed = discord.Embed(
            title=f"{EMOJI_TICK} Ticket Claimed",
            description=f"{interaction.user.mention} has claimed this ticket and will be assisting you.",
            color=discord.Color.green()
        )
        await interaction.channel.edit(topic=f"Claimed Staff: {interaction.user} | ID: {interaction.user.id}")
        await interaction.response.send_message(embed=embed)

    @discord.ui.button(label="Generate Transcript", style=discord.ButtonStyle.secondary, emoji="📜", custom_id="ticket_btn_transcript")
    async def transcript_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        file_buffer, msg_count = await self.cog.generate_transcript_file(interaction.channel)
        
        embed = discord.Embed(
            title=f"{EMOJI_TICK} Transcript Generated",
            description=f"Exported **{msg_count}** messages from {interaction.channel.mention}.",
            color=discord.Color.blue()
        )
        await interaction.followup.send(embed=embed, file=discord.File(file_buffer, filename=f"transcript-{interaction.channel.name}.txt"), ephemeral=True)

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="ticket_btn_close")
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🔒 Archiving ticket and generating transcript in 5 seconds...", ephemeral=False)
        await self.cog.close_ticket_logic(interaction.channel, interaction.user, reason="Closed via control panel")


class TicketDropdown(discord.ui.Select):
    """Category selector dropdown on the main setup panel."""
    def __init__(self, cog: "TicketCog"):
        self.cog = cog
        options = [
            discord.SelectOption(label="General Support", description="General questions or server assistance.", emoji="❓", value="general"),
            discord.SelectOption(label="Player Report / Bug", description="Report rule breakers or system bugs.", emoji="🛡️", value="report"),
            discord.SelectOption(label="Billing & Donations", description="Inquiries regarding perks, roles, or payments.", emoji="💎", value="billing")
        ]
        super().__init__(placeholder="Choose a ticket category...", min_values=1, max_values=1, options=options, custom_id="ticket_panel_dropdown")

    async def callback(self, interaction: discord.Interaction):
        modal = TicketReasonModal(self.cog, self.values[0])
        await interaction.response.send_modal(modal)


class TicketPanelView(discord.ui.View):
    """View container for the public setup panel."""
    def __init__(self, cog: "TicketCog"):
        super().__init__(timeout=None)
        self.add_item(TicketDropdown(cog))


class TicketCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        """Initializes database schema and registers persistent UI views."""
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS ticket_settings (
                    guild_id INTEGER PRIMARY KEY,
                    category_id INTEGER,
                    support_role_id INTEGER,
                    transcript_channel_id INTEGER,
                    ticket_counter INTEGER DEFAULT 0
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS active_tickets (
                    channel_id INTEGER PRIMARY KEY,
                    guild_id INTEGER,
                    user_id INTEGER,
                    ticket_num INTEGER,
                    category TEXT,
                    subject TEXT
                )
            """)
            await db.commit()

        self.bot.add_view(TicketPanelView(self))
        self.bot.add_view(TicketControlView(self))

    async def get_support_role(self, guild_id: int) -> Optional[int]:
        """Fetches configured support role ID."""
        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute("SELECT support_role_id FROM ticket_settings WHERE guild_id = ?", (guild_id,)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None

    async def generate_transcript_file(self, channel: discord.TextChannel) -> tuple[io.BytesIO, int]:
        """Fetches message history and formats a TXT file transcript."""
        messages = []
        async for msg in channel.history(limit=1000, oldest_first=True):
            messages.append(msg)

        lines = [f"=== TRANSCRIPT FOR #{channel.name} ({channel.guild.name}) ===", f"Generated On: {discord.utils.utcnow()}\n"]
        for m in messages:
            timestamp = m.created_at.strftime("%Y-%m-%d %H:%M:%S")
            attachments = f" [Attachments: {', '.join([a.url for a in m.attachments])}]" if m.attachments else ""
            lines.append(f"[{timestamp}] {m.author} ({m.author.id}): {m.clean_content}{attachments}")

        buffer = io.BytesIO("\n".join(lines).encode("utf-8"))
        return buffer, len(messages)

    async def create_ticket_channel(self, interaction: discord.Interaction, category_type: str, subject: str, description: str):
        """Creates an isolated text channel for the ticket."""
        guild = interaction.guild
        user = interaction.user

        async with aiosqlite.connect(DB_FILE) as db:
            db.row_factory = sqlite3.Row
            async with db.execute("SELECT * FROM ticket_settings WHERE guild_id = ?", (guild.id,)) as cursor:
                settings = await cursor.fetchone()

        if not settings or not settings["category_id"]:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} System Unconfigured",
                description="The ticket system is not configured. Ask an admin to run `/ticket-setup`.",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # Check existing active tickets
        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute("SELECT channel_id FROM active_tickets WHERE guild_id = ? AND user_id = ?", (guild.id, user.id)) as cursor:
                existing = await cursor.fetchone()
                if existing:
                    ch = guild.get_channel(existing[0])
                    if ch:
                        embed = discord.Embed(
                            title=f"{EMOJI_CROSS} Ticket Already Active",
                            description=f"You already have an active ticket open in {ch.mention}.",
                            color=discord.Color.red()
                        )
                        return await interaction.response.send_message(embed=embed, ephemeral=True)

        category = guild.get_channel(settings["category_id"])
        support_role = guild.get_role(settings["support_role_id"]) if settings["support_role_id"] else None

        ticket_num = settings["ticket_counter"] + 1
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("UPDATE ticket_settings SET ticket_counter = ? WHERE guild_id = ?", (ticket_num, guild.id))
            await db.commit()

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False, send_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }
        if support_role:
            overwrites[support_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_messages=True)

        channel_name = f"ticket-{ticket_num:04d}"
        ticket_channel = await guild.create_text_channel(
            name=channel_name,
            category=category,
            overwrites=overwrites,
            topic=f"Ticket Author: {user} ({user.id}) | Subject: {subject}",
            reason=f"Ticket opened by {user}"
        )

        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("""
                INSERT INTO active_tickets (channel_id, guild_id, user_id, ticket_num, category, subject)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (ticket_channel.id, guild.id, user.id, ticket_num, category_type, subject))
            await db.commit()

        welcome_embed = discord.Embed(
            title=f"{EMOJI_TICK} Support Ticket #{ticket_num:04d}",
            description=f"Welcome {user.mention}! Support staff will be with you shortly.",
            color=discord.Color.blue()
        )
        welcome_embed.add_field(name="Category", value=f"`{category_type.title()}`", inline=True)
        welcome_embed.add_field(name="Subject", value=f"`{subject}`", inline=True)
        welcome_embed.add_field(name="Description / Details", value=f"```\n{description}\n```", inline=False)
        welcome_embed.set_footer(text="Use controls below to claim, log, or close.", icon_url=self.bot.user.display_avatar.url)
        welcome_embed.timestamp = discord.utils.utcnow()

        ping_text = f"{user.mention}"
        if support_role:
            ping_text += f" | {support_role.mention}"

        view = TicketControlView(self)
        await ticket_channel.send(content=ping_text, embed=welcome_embed, view=view)

        resp_embed = discord.Embed(
            title=f"{EMOJI_TICK} Ticket Channel Created",
            description=f"Your ticket has been opened in {ticket_channel.mention}.",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=resp_embed, ephemeral=True)

    async def close_ticket_logic(self, channel: discord.TextChannel, moderator: discord.User, reason: str = "Closed by moderator"):
        """Generates transcripts, logs to transcript channel, and deletes channel."""
        guild = channel.guild

        async with aiosqlite.connect(DB_FILE) as db:
            db.row_factory = sqlite3.Row
            async with db.execute("SELECT * FROM ticket_settings WHERE guild_id = ?", (guild.id,)) as cursor:
                settings = await cursor.fetchone()

        # Generate Transcript
        buffer, count = await self.generate_transcript_file(channel)

        if settings and settings["transcript_channel_id"]:
            log_ch = guild.get_channel(settings["transcript_channel_id"])
            if log_ch:
                log_embed = discord.Embed(
                    title=f"📜 Ticket Transcript — #{channel.name}",
                    description=f"Ticket closed by {moderator.mention}.",
                    color=discord.Color.purple()
                )
                log_embed.add_field(name="Messages Logged", value=f"`{count}`", inline=True)
                log_embed.add_field(name="Reason", value=f"`{reason}`", inline=True)
                log_embed.timestamp = discord.utils.utcnow()
                try:
                    await log_ch.send(embed=log_embed, file=discord.File(buffer, filename=f"{channel.name}-transcript.txt"))
                except Exception:
                    pass

        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("DELETE FROM active_tickets WHERE channel_id = ?", (channel.id,))
            await db.commit()

        try:
            await channel.delete(reason=f"Ticket closed by {moderator} | {reason}")
        except Exception:
            pass

    # ==========================================
    # SLASH COMMAND: /ticket-setup
    # ==========================================
    @app_commands.command(
        name="ticket-setup",
        description="Initialize the automated ticket system panel and destination category."
    )
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(
        category="Category channel where tickets will be created",
        support_role="Role designated as ticket support staff",
        transcript_channel="Optional: Channel where closed ticket transcripts will be posted"
    )
    async def ticket_setup_command(
        self,
        interaction: discord.Interaction,
        category: discord.CategoryChannel,
        support_role: discord.Role,
        transcript_channel: Optional[discord.TextChannel] = None
    ):
        guild = interaction.guild

        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("""
                INSERT OR REPLACE INTO ticket_settings 
                (guild_id, category_id, support_role_id, transcript_channel_id, ticket_counter)
                VALUES (?, ?, ?, ?, COALESCE((SELECT ticket_counter FROM ticket_settings WHERE guild_id = ?), 0))
            """, (guild.id, category.id, support_role.id, transcript_channel.id if transcript_channel else None, guild.id))
            await db.commit()

        panel_embed = discord.Embed(
            title="🎟️ Support & Help Desk",
            description="Need assistance, want to report a user, or have billing questions?\nSelect an option from the dropdown menu below to open a private ticket channel with our team.",
            color=discord.Color.blue()
        )
        panel_embed.set_thumbnail(url=guild.icon.url if guild.icon else self.bot.user.display_avatar.url)
        panel_embed.set_footer(text="Phantom Ticket Systems • Select a category below", icon_url=self.bot.user.display_avatar.url)

        view = TicketPanelView(self)
        await interaction.channel.send(embed=panel_embed, view=view)

        resp_embed = discord.Embed(
            title=f"{EMOJI_TICK} Ticket System Configured",
            description=f"Posted setup panel in {interaction.channel.mention}.\n• **Category:** {category.name}\n• **Staff Role:** {support_role.mention}",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=resp_embed, ephemeral=True)

    # ==========================================
    # SLASH COMMAND: /ticket-close
    # ==========================================
    @app_commands.command(
        name="ticket-close",
        description="Close and archive the current ticket channel with optional reason."
    )
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.describe(reason="Reason for closing the ticket")
    async def ticket_close_command(self, interaction: discord.Interaction, reason: str = "Closed by moderator"):
        await interaction.response.send_message("🔒 Closing ticket in 5 seconds...", ephemeral=False)
        await self.close_ticket_logic(interaction.channel, interaction.user, reason=reason)

    # ==========================================
    # SLASH COMMAND: /ticket-add
    # ==========================================
    @app_commands.command(
        name="ticket-add",
        description="Add a member to the current ticket channel."
    )
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.describe(user="Member to grant access to this ticket")
    async def ticket_add_command(self, interaction: discord.Interaction, user: discord.Member):
        channel = interaction.channel
        await channel.set_permissions(user, read_messages=True, send_messages=True)

        embed = discord.Embed(
            title=f"{EMOJI_TICK} Member Added",
            description=f"Granted {user.mention} access to this ticket.",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)

    # ==========================================
    # SLASH COMMAND: /ticket-remove
    # ==========================================
    @app_commands.command(
        name="ticket-remove",
        description="Remove a member from the current ticket channel."
    )
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.describe(user="Member to remove from this ticket")
    async def ticket_remove_command(self, interaction: discord.Interaction, user: discord.Member):
        channel = interaction.channel
        await channel.set_permissions(user, overwrite=None)

        embed = discord.Embed(
            title=f"{EMOJI_TICK} Member Removed",
            description=f"Revoked {user.mention}'s access to this ticket.",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)

    # ==========================================
    # ERROR HANDLING
    # ==========================================
    @ticket_setup_command.error
    @ticket_close_command.error
    @ticket_add_command.error
    @ticket_remove_command.error
    async def ticket_error_handler(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Permission Denied",
                description=f"{interaction.user.mention}, you lack the required permissions to run this command.",
                color=discord.Color.red()
            )
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(TicketCog(bot))
