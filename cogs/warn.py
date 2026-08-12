import sqlite3
import aiosqlite
import discord
from datetime import timedelta
from discord import app_commands
from discord.ext import commands
from typing import Optional, List

# Custom Emoji Constants
EMOJI_TICK = "<a:Tick:1536982741537656832>"
EMOJI_CROSS = "<:Cross:1536982744008106055>"
DB_FILE = "warnings.db"


class WarnControlView(discord.ui.View):
    """Interactive control view for managing user infractions directly from embeds."""
    def __init__(self, cog: "WarnCog", guild_id: int, target: discord.Member, moderator: discord.Member):
        super().__init__(timeout=120)
        self.cog = cog
        self.guild_id = guild_id
        self.target = target
        self.moderator = moderator

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.moderator.id:
            await interaction.response.send_message(
                f"{EMOJI_CROSS} Only {self.moderator.mention} can interact with these controls.",
                ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="View History", style=discord.ButtonStyle.primary, emoji="📜")
    async def view_history(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Displays full warning history for target user."""
        warnings = await self.cog.get_user_warnings(self.guild_id, self.target.id)
        if not warnings:
            embed = discord.Embed(
                title=f"{EMOJI_TICK} Clean Record",
                description=f"{self.target.mention} has no active warning records.",
                color=discord.Color.green()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        embed = discord.Embed(
            title=f"⚠️ Complete Infraction History — {self.target.name}",
            description=f"Total Infractions Logged: `{len(warnings)}`",
            color=discord.Color.gold()
        )
        embed.set_thumbnail(url=self.target.display_avatar.url)

        for w in warnings[:10]:
            mod = interaction.guild.get_member(w["moderator_id"])
            mod_mention = mod.mention if mod else f"`ID: {w['moderator_id']}`"
            embed.add_field(
                name=f"Warn ID: #{w['warn_id']}",
                value=f"• **Reason:** `{w['reason']}`\n• **Moderator:** {mod_mention}\n• **Timestamp:** `{w['timestamp']}`",
                inline=False
            )

        embed.set_footer(text=f"Target ID: {self.target.id}", icon_url=interaction.user.display_avatar.url)
        embed.timestamp = discord.utils.utcnow()
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Clear Record", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def clear_record(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Wipes all warnings for the target user."""
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(
                f"{EMOJI_CROSS} You need `Administrator` permissions to clear member records.",
                ephemeral=True
            )

        async with aiosqlite.connect(DB_FILE) as db:
            cursor = await db.execute(
                "DELETE FROM user_warnings WHERE guild_id = ? AND user_id = ?",
                (self.guild_id, self.target.id)
            )
            await db.commit()
            deleted_count = cursor.rowcount

        embed = discord.Embed(
            title=f"{EMOJI_TICK} Record Cleared",
            description=f"Wiped **{deleted_count}** warning logs for {self.target.mention}.",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class WarnCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        """Initializes SQLite database table for warning records on cog load."""
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS user_warnings (
                    warn_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER,
                    user_id INTEGER,
                    moderator_id INTEGER,
                    reason TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.commit()

    async def get_user_warnings(self, guild_id: int, user_id: int) -> List[dict]:
        """Fetches all warning records for a user from SQLite."""
        async with aiosqlite.connect(DB_FILE) as db:
            db.row_factory = sqlite3.Row
            async with db.execute(
                "SELECT * FROM user_warnings WHERE guild_id = ? AND user_id = ? ORDER BY timestamp DESC",
                (guild_id, user_id)
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    # ==========================================
    # SLASH COMMAND: /warn
    # ==========================================
    @app_commands.command(
        name="warn",
        description="Issue a formal warning and log it permanently in the user's record."
    )
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.bot_has_permissions(moderate_members=True)
    @app_commands.describe(
        user="The member to issue a warning to",
        reason="Detailed reason for issuing this warning"
    )
    async def warn_command(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        reason: str
    ):
        guild = interaction.guild
        moderator = interaction.user

        # ----------------------------------------------------
        # HIERARCHY & VALIDATION CHECKS
        # ----------------------------------------------------
        if user.id == moderator.id:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Action Prohibited",
                description="You cannot issue a warning to yourself.",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        if user.id == self.bot.user.id:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Action Prohibited",
                description="I cannot warn myself.",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        if user.top_role >= moderator.top_role and moderator.id != guild.owner_id:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Hierarchy Error",
                description=f"You cannot warn {user.mention} because their highest role ({user.top_role.mention}) is equal to or higher than yours ({moderator.top_role.mention}).",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # ----------------------------------------------------
        # LOG WARNING IN DATABASE
        # ----------------------------------------------------
        async with aiosqlite.connect(DB_FILE) as db:
            cursor = await db.execute("""
                INSERT INTO user_warnings (guild_id, user_id, moderator_id, reason)
                VALUES (?, ?, ?, ?)
            """, (guild.id, user.id, moderator.id, reason))
            await db.commit()
            warn_id = cursor.lastrowid

        history = await self.get_user_warnings(guild.id, user.id)
        total_warns = len(history)

        # ----------------------------------------------------
        # DIRECT MESSAGE NOTIFICATION
        # ----------------------------------------------------
        dm_sent = False
        dm_embed = discord.Embed(
            title=f"{EMOJI_CROSS} Official Warning Issued",
            description=f"An official warning has been added to your record in **{guild.name}**.",
            color=discord.Color.gold()
        )
        dm_embed.add_field(name="Reason", value=f"```\n{reason}\n```", inline=False)
        dm_embed.add_field(name="Total Record Warnings", value=f"`{total_warns}`", inline=True)
        dm_embed.add_field(name="Moderator", value=f"{moderator} (`{moderator.id}`)", inline=True)
        dm_embed.set_footer(text="Infractions remain on your permanent moderation profile.")
        dm_embed.timestamp = discord.utils.utcnow()

        try:
            await user.send(embed=dm_embed)
            dm_sent = True
        except (discord.Forbidden, discord.HTTPException):
            dm_sent = False

        # ----------------------------------------------------
        # AUTOMATED TIMEOUT ESCALATIONS (NO KICKS)
        # ----------------------------------------------------
        auto_action = "Logged to Permanent Record"
        
        # Escalation Rule 1: 3 Warnings -> 1 Hour Timeout
        if total_warns == 3:
            try:
                await user.timeout(timedelta(hours=1), reason="Automated Escalation: Reached 3 warnings in record.")
                auto_action = "Muted for 1 Hour (3 Warnings Reached)"
            except Exception:
                auto_action = "Record Logged (Timeout Failed - Check Hierarchy)"

        # Escalation Rule 2: 5 Warnings -> 24 Hour Timeout
        elif total_warns >= 5:
            try:
                await user.timeout(timedelta(hours=24), reason="Automated Escalation: Reached 5+ warnings in record.")
                auto_action = "Muted for 24 Hours (5+ Warnings Reached)"
            except Exception:
                auto_action = "Record Logged (Timeout Failed - Check Hierarchy)"

        # ----------------------------------------------------
        # SERVER CHANNEL CONFIRMATION EMBED
        # ----------------------------------------------------
        server_embed = discord.Embed(
            title=f"{EMOJI_TICK} Infraction Recorded Successfully",
            description=f"Issued Warning `#{warn_id}` to {user.mention}.",
            color=discord.Color.green()
        )
        server_embed.set_thumbnail(url=user.display_avatar.url)
        server_embed.add_field(name="Target Member", value=f"{user.name} (`{user.id}`)", inline=True)
        server_embed.add_field(name="Total Infractions", value=f"`{total_warns}`", inline=True)
        server_embed.add_field(name="DM Notification", value=f"`{'Sent' if dm_sent else 'Failed (DMs Closed)'}`", inline=True)
        server_embed.add_field(name="Status / Action", value=f"`{auto_action}`", inline=False)
        server_embed.add_field(name="Reason", value=f"```\n{reason}\n```", inline=False)
        server_embed.set_footer(text=f"Target ID: {user.id} • Warn ID: #{warn_id}", icon_url=self.bot.user.display_avatar.url)
        server_embed.timestamp = discord.utils.utcnow()

        view = WarnControlView(self, guild.id, user, moderator)
        await interaction.response.send_message(embed=server_embed, view=view)

    # ==========================================
    # SLASH COMMAND: /warnings
    # ==========================================
    @app_commands.command(
        name="warnings",
        description="Inspect permanent warning records for a server member."
    )
    @app_commands.guild_only()
    @app_commands.describe(user="The member whose warnings you want to view")
    async def warnings_command(
        self, 
        interaction: discord.Interaction, 
        user: Optional[discord.Member] = None
    ):
        target = user or interaction.user
        guild_id = interaction.guild_id

        warnings = await self.get_user_warnings(guild_id, target.id)

        if not warnings:
            embed = discord.Embed(
                title=f"{EMOJI_TICK} Clean Moderation Record",
                description=f"{target.mention} has no warning records in this server.",
                color=discord.Color.green()
            )
            return await interaction.response.send_message(embed=embed)

        embed = discord.Embed(
            title=f"⚠️ Permanent Warning Record — {target.name}",
            description=f"Total Infractions: **{len(warnings)}**",
            color=discord.Color.gold()
        )
        embed.set_thumbnail(url=target.display_avatar.url)

        for w in warnings[:10]:
            mod = interaction.guild.get_member(w["moderator_id"])
            mod_text = mod.mention if mod else f"`ID: {w['moderator_id']}`"
            embed.add_field(
                name=f"Warn ID: #{w['warn_id']}",
                value=f"• **Reason:** `{w['reason']}`\n• **Moderator:** {mod_text}\n• **Timestamp:** `{w['timestamp']}`",
                inline=False
            )

        if len(warnings) > 10:
            embed.set_footer(text=f"Showing 10 newest of {len(warnings)} recorded infractions.")
        else:
            embed.set_footer(text=f"Target ID: {target.id}")

        embed.timestamp = discord.utils.utcnow()
        
        view = WarnControlView(self, guild_id, target, interaction.user)
        await interaction.response.send_message(embed=embed, view=view)

    # ==========================================
    # SLASH COMMAND: /clearwarns
    # ==========================================
    @app_commands.command(
        name="clearwarns",
        description="Clear all warning records for a server member."
    )
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(user="The member whose warnings will be wiped")
    async def clearwarns_command(
        self, 
        interaction: discord.Interaction, 
        user: discord.Member
    ):
        async with aiosqlite.connect(DB_FILE) as db:
            cursor = await db.execute(
                "DELETE FROM user_warnings WHERE guild_id = ? AND user_id = ?",
                (interaction.guild_id, user.id)
            )
            await db.commit()
            deleted_count = cursor.rowcount

        if deleted_count == 0:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} No Records Found",
                description=f"{user.mention} has no warnings to clear.",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        embed = discord.Embed(
            title=f"{EMOJI_TICK} Records Wiped",
            description=f"Successfully wiped **{deleted_count}** warning record(s) from {user.mention}'s profile.",
            color=discord.Color.green()
        )
        embed.set_footer(text=f"Action executed by {interaction.user}", icon_url=interaction.user.display_avatar.url)
        embed.timestamp = discord.utils.utcnow()

        await interaction.response.send_message(embed=embed)

    # ==========================================
    # SLASH COMMAND: /removewarn
    # ==========================================
    @app_commands.command(
        name="removewarn",
        description="Delete a single specific warning entry by its ID."
    )
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.describe(warn_id="The numeric Warn ID to delete")
    async def removewarn_command(
        self, 
        interaction: discord.Interaction, 
        warn_id: int
    ):
        async with aiosqlite.connect(DB_FILE) as db:
            cursor = await db.execute(
                "DELETE FROM user_warnings WHERE guild_id = ? AND warn_id = ?",
                (interaction.guild_id, warn_id)
            )
            await db.commit()
            deleted_rows = cursor.rowcount

        if deleted_rows == 0:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Warn ID Not Found",
                description=f"No warning entry with ID `#{warn_id}` exists for this server.",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        embed = discord.Embed(
            title=f"{EMOJI_TICK} Entry Deleted",
            description=f"Successfully deleted Warning `#{warn_id}` from server records.",
            color=discord.Color.green()
        )
        embed.timestamp = discord.utils.utcnow()
        await interaction.response.send_message(embed=embed)

    # ==========================================
    # ERROR HANDLING
    # ==========================================
    @warn_command.error
    @clearwarns_command.error
    @removewarn_command.error
    async def warn_error_handler(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            missing_perms = ", ".join([f"`{perm}`" for perm in error.missing_permissions])
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Permission Denied",
                description=f"{interaction.user.mention}, you lack required permission(s): {missing_perms}",
                color=discord.Color.red()
            )
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)

        elif isinstance(error, app_commands.BotMissingPermissions):
            missing_perms = ", ".join([f"`{perm}`" for perm in error.missing_permissions])
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Bot Permission Required",
                description=f"I am missing required permission(s): {missing_perms}",
                color=discord.Color.red()
            )
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)

        else:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Unexpected Error",
                description=f"An error occurred: `{str(error)}`",
                color=discord.Color.red()
            )
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(WarnCog(bot))
      
