import sqlite3
import aiosqlite
import re
from datetime import datetime, timedelta
from typing import Optional, List
import discord
from discord import app_commands
from discord.ext import commands, tasks

# Custom Emoji Constants
EMOJI_TICK = "<a:Tick:1536982741537656832>"
EMOJI_CROSS = "<:Cross:1536982744008106055>"
DB_FILE = "lockdowns.db"


def parse_duration(duration_str: str) -> Optional[timedelta]:
    """Parses time strings like '10m', '1h', '2d' into timedelta objects."""
    match = re.match(r"^(\d+)\s*([sSmMhHdD])$", duration_str.strip())
    if not match:
        return None

    value, unit = int(match.group(1)), match.group(2).lower()
    if unit == "s":
        return timedelta(seconds=value)
    elif unit == "m":
        return timedelta(minutes=value)
    elif unit == "h":
        return timedelta(hours=value)
    elif unit == "d":
        return timedelta(days=value)
    return None


class LockdownControlView(discord.ui.View):
    """Interactive control view attached to lockdown announcements."""
    def __init__(self, cog: "LockdownCog", channel: discord.TextChannel, author: discord.Member):
        super().__init__(timeout=None)
        self.cog = cog
        self.channel = channel
        self.author = author

    @discord.ui.button(label="Unlock Channel", style=discord.ButtonStyle.success, emoji="🔓", custom_id="lockdown_unlock_btn")
    async def unlock_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message(
                f"{EMOJI_CROSS} You need `Manage Channels` permissions to unlock this channel.",
                ephemeral=True
            )

        await self.cog.unlock_channel_logic(
            guild=interaction.guild,
            channel=self.channel,
            moderator=interaction.user,
            reason="Unlocked via announcement button."
        )

        embed = discord.Embed(
            title=f"{EMOJI_TICK} Channel Unlocked",
            description=f"{self.channel.mention} has been restored by {interaction.user.mention}.",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class LockdownCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.auto_unlock_check.start()

    def cog_unload(self):
        self.auto_unlock_check.cancel()

    async def cog_load(self):
        """Initializes SQLite database table on cog load."""
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS active_lockdowns (
                    channel_id INTEGER PRIMARY KEY,
                    guild_id INTEGER,
                    moderator_id INTEGER,
                    unlock_time TEXT,
                    reason TEXT
                )
            """)
            await db.commit()

    # ==========================================
    # BACKGROUND TASK: AUTOMATED UNLOCK SCHEDULER
    # ==========================================
    @tasks.loop(seconds=15)
    async def auto_unlock_check(self):
        """Monitors scheduled auto-unlock timestamps and releases channel lockdowns."""
        now = discord.utils.utcnow()
        async with aiosqlite.connect(DB_FILE) as db:
            db.row_factory = sqlite3.Row
            async with db.execute("SELECT * FROM active_lockdowns WHERE unlock_time IS NOT NULL") as cursor:
                records = await cursor.fetchall()

            for rec in records:
                unlock_dt = datetime.fromisoformat(rec["unlock_time"])
                if now >= unlock_dt:
                    guild = self.bot.get_guild(rec["guild_id"])
                    if guild:
                        channel = guild.get_channel(rec["channel_id"])
                        if channel and isinstance(channel, discord.TextChannel):
                            try:
                                await self.unlock_channel_logic(
                                    guild=guild,
                                    channel=channel,
                                    moderator=guild.me,
                                    reason="Scheduled auto-lockdown duration expired."
                                )
                            except Exception:
                                pass
                    await db.execute("DELETE FROM active_lockdowns WHERE channel_id = ?", (rec["channel_id"],))
            await db.commit()

    @auto_unlock_check.before_loop
    async def before_auto_unlock_check(self):
        await self.bot.wait_until_ready()

    # ==========================================
    # CORE UNLOCK LOGIC HELPER
    # ==========================================
    async def unlock_channel_logic(
        self,
        guild: discord.Guild,
        channel: discord.TextChannel,
        moderator: discord.Member,
        reason: str
    ):
        everyone_role = guild.default_role
        current_overwrite = channel.overwrites_for(everyone_role)

        current_overwrite.send_messages = None
        current_overwrite.send_messages_in_threads = None
        await channel.set_permissions(
            everyone_role,
            overwrite=current_overwrite,
            reason=f"Unlocked by {moderator} | Reason: {reason}"
        )

        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("DELETE FROM active_lockdowns WHERE channel_id = ?", (channel.id,))
            await db.commit()

        announcement = discord.Embed(
            title="🔓 Channel Unlocked",
            description="The channel lockdown has ended. Standard message permissions have been restored.",
            color=discord.Color.green()
        )
        announcement.set_footer(text=f"Unlocked by {moderator}", icon_url=moderator.display_avatar.url)
        announcement.timestamp = discord.utils.utcnow()

        try:
            await channel.send(embed=announcement)
        except Exception:
            pass

    # ==========================================
    # SLASH COMMAND: /lockdown
    # ==========================================
    @app_commands.command(
        name="lockdown",
        description="Lock a channel to prevent @everyone from chatting, with optional auto-unlock timer."
    )
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.bot_has_permissions(manage_channels=True)
    @app_commands.describe(
        channel="Channel to lock (Defaults to current channel)",
        duration="Optional: Auto-unlock duration (e.g., 10m, 1h, 1d)",
        reason="Reason for locking down the channel"
    )
    async def lockdown_command(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
        duration: Optional[str] = None,
        reason: str = "No reason provided"
    ):
        target_channel = channel or interaction.channel
        guild = interaction.guild
        moderator = interaction.user

        # Parse auto-unlock duration
        unlock_time = None
        duration_delta = None
        if duration:
            duration_delta = parse_duration(duration)
            if not duration_delta:
                embed = discord.Embed(
                    title=f"{EMOJI_CROSS} Invalid Duration Format",
                    description="Use standard time units:\n• `10m` = 10 Minutes\n• `1h` = 1 Hour\n• `1d` = 1 Day",
                    color=discord.Color.red()
                )
                return await interaction.response.send_message(embed=embed, ephemeral=True)
            unlock_time = discord.utils.utcnow() + duration_delta

        everyone_role = guild.default_role
        current_overwrite = target_channel.overwrites_for(everyone_role)

        if current_overwrite.send_messages is False:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Already Locked",
                description=f"{target_channel.mention} is already in lockdown mode.",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        try:
            current_overwrite.send_messages = False
            current_overwrite.send_messages_in_threads = False
            await target_channel.set_permissions(
                everyone_role,
                overwrite=current_overwrite,
                reason=f"Lockdown by {moderator} | Reason: {reason}"
            )
        except Exception as e:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Lockdown Failed",
                description=f"An error occurred while locking {target_channel.mention}: `{str(e)}`",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # Record lockdown state in database
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("""
                INSERT OR REPLACE INTO active_lockdowns (channel_id, guild_id, moderator_id, unlock_time, reason)
                VALUES (?, ?, ?, ?, ?)
            """, (
                target_channel.id, guild.id, moderator.id,
                unlock_time.isoformat() if unlock_time else None, reason
            ))
            await db.commit()

        # Send announcement in locked channel with interactive unlock view
        channel_announcement = discord.Embed(
            title="🔒 Channel Locked Down",
            description="This channel has been locked by server moderation.\nStandard members cannot send messages until it is unlocked.",
            color=discord.Color.dark_red()
        )
        if unlock_time:
            channel_announcement.add_field(
                name="Auto-Unlock Timer",
                value=f"<t:{int(unlock_time.timestamp())}:R> (`{duration}`)",
                inline=False
            )
        channel_announcement.add_field(name="Reason", value=f"```\n{reason}\n```", inline=False)
        channel_announcement.set_footer(text=f"Action by {moderator}", icon_url=moderator.display_avatar.url)
        channel_announcement.timestamp = discord.utils.utcnow()

        view = LockdownControlView(self, target_channel, moderator)
        try:
            await target_channel.send(embed=channel_announcement, view=view)
        except Exception:
            pass

        # Response embed
        server_embed = discord.Embed(
            title=f"{EMOJI_TICK} Lockdown Executed Successfully",
            description=f"Successfully locked {target_channel.mention}.",
            color=discord.Color.green()
        )
        server_embed.add_field(name="Target Channel", value=target_channel.mention, inline=True)
        server_embed.add_field(name="Moderator", value=moderator.mention, inline=True)
        if unlock_time:
            server_embed.add_field(name="Auto-Unlock", value=f"<t:{int(unlock_time.timestamp())}:R>", inline=True)
        server_embed.add_field(name="Reason", value=f"```\n{reason}\n```", inline=False)
        server_embed.set_footer(text=f"Channel ID: {target_channel.id}", icon_url=self.bot.user.display_avatar.url)
        server_embed.timestamp = discord.utils.utcnow()

        if interaction.channel.id == target_channel.id:
            await interaction.response.send_message(embed=server_embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=server_embed)

    # ==========================================
    # SLASH COMMAND: /unlock
    # ==========================================
    @app_commands.command(
        name="unlock",
        description="Unlock a channel to restore chatting permissions for @everyone."
    )
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.bot_has_permissions(manage_channels=True)
    @app_commands.describe(
        channel="Channel to unlock (Defaults to current channel)",
        reason="Reason for unlocking the channel"
    )
    async def unlock_command(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
        reason: str = "No reason provided"
    ):
        target_channel = channel or interaction.channel
        guild = interaction.guild

        everyone_role = guild.default_role
        current_overwrite = target_channel.overwrites_for(everyone_role)

        if current_overwrite.send_messages is None or current_overwrite.send_messages is True:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Channel Not Locked",
                description=f"{target_channel.mention} is not currently locked.",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        try:
            await self.unlock_channel_logic(guild, target_channel, interaction.user, reason)
        except Exception as e:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Unlock Failed",
                description=f"An error occurred while unlocking {target_channel.mention}: `{str(e)}`",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        server_embed = discord.Embed(
            title=f"{EMOJI_TICK} Channel Unlocked Successfully",
            description=f"Restored permissions for {target_channel.mention}.",
            color=discord.Color.green()
        )
        server_embed.add_field(name="Target Channel", value=target_channel.mention, inline=True)
        server_embed.add_field(name="Moderator", value=interaction.user.mention, inline=True)
        server_embed.add_field(name="Reason", value=f"```\n{reason}\n```", inline=False)
        server_embed.set_footer(text=f"Channel ID: {target_channel.id}", icon_url=self.bot.user.display_avatar.url)
        server_embed.timestamp = discord.utils.utcnow()

        await interaction.response.send_message(embed=server_embed)

    # ==========================================
    # SLASH COMMAND: /lockdown-server
    # ==========================================
    @app_commands.command(
        name="lockdown-server",
        description="EMERGENCY: Lock down ALL text channels in the entire server at once."
    )
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.bot_has_permissions(manage_channels=True)
    @app_commands.describe(reason="Reason for triggering server-wide lockdown")
    async def lockdown_server_command(self, interaction: discord.Interaction, reason: str = "Server Emergency / Anti-Raid"):
        guild = interaction.guild
        await interaction.response.defer()

        everyone_role = guild.default_role
        locked_channels = []

        for ch in guild.text_channels:
            overwrite = ch.overwrites_for(everyone_role)
            if overwrite.send_messages is not False:
                try:
                    overwrite.send_messages = False
                    overwrite.send_messages_in_threads = False
                    await ch.set_permissions(everyone_role, overwrite=overwrite, reason=f"Server Lockdown by {interaction.user}")
                    locked_channels.append(ch)

                    async with aiosqlite.connect(DB_FILE) as db:
                        await db.execute("""
                            INSERT OR REPLACE INTO active_lockdowns (channel_id, guild_id, moderator_id, unlock_time, reason)
                            VALUES (?, ?, ?, NULL, ?)
                        """, (ch.id, guild.id, interaction.user.id, reason))
                        await db.commit()
                except Exception:
                    pass

        embed = discord.Embed(
            title=f"{EMOJI_TICK} MASS SERVER LOCKDOWN EXECUTED",
            description=f"Successfully locked **{len(locked_channels)}** text channels across **{guild.name}**.",
            color=discord.Color.dark_red()
        )
        embed.add_field(name="Moderator", value=interaction.user.mention, inline=True)
        embed.add_field(name="Reason", value=f"```\n{reason}\n```", inline=False)
        embed.set_footer(text="Use /unlock on individual channels or run server unlock to clear.", icon_url=self.bot.user.display_avatar.url)
        embed.timestamp = discord.utils.utcnow()

        await interaction.followup.send(embed=embed)

    # ==========================================
    # ERROR HANDLING
    # ==========================================
    @lockdown_command.error
    @unlock_command.error
    @lockdown_server_command.error
    async def lockdown_error_handler(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            missing_perms = ", ".join([f"`{perm}`" for perm in error.missing_permissions])
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Permission Denied",
                description=f"{interaction.user.mention}, you lack permission(s): {missing_perms}",
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


async def setup(bot: commands.Bot):
    await bot.add_cog(LockdownCog(bot))

