import sqlite3
import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, List

# Custom Emoji Constants
EMOJI_TICK = "<a:Tick:1536982741537656832>"
EMOJI_CROSS = "<:Cross:1536982744008106055>"
DB_FILE = "lockdowns.db"


class UnlockdownControlView(discord.ui.View):
    """Interactive control view attached to unlock announcements for instant re-locking."""
    def __init__(self, cog: "UnlockdownCog", channel: discord.TextChannel, moderator: discord.Member):
        super().__init__(timeout=120)
        self.cog = cog
        self.channel = channel
        self.moderator = moderator

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message(
                f"{EMOJI_CROSS} You need `Manage Channels` permissions to manage lockdowns.",
                ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Relock Channel", style=discord.ButtonStyle.danger, emoji="🔒")
    async def relock_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Allows moderators to instantly relock the channel if necessary."""
        everyone_role = interaction.guild.default_role
        current_overwrite = self.channel.overwrites_for(everyone_role)

        current_overwrite.send_messages = False
        current_overwrite.send_messages_in_threads = False

        try:
            await self.channel.set_permissions(
                everyone_role,
                overwrite=current_overwrite,
                reason=f"Relocked via UI button by {interaction.user}"
            )
            
            # Re-insert into database
            async with aiosqlite.connect(DB_FILE) as db:
                await db.execute("""
                    INSERT OR REPLACE INTO active_lockdowns (channel_id, guild_id, moderator_id, unlock_time, reason)
                    VALUES (?, ?, ?, NULL, ?)
                """, (self.channel.id, interaction.guild.id, interaction.user.id, "Emergency Relock"))
                await db.commit()

            embed = discord.Embed(
                title=f"{EMOJI_TICK} Channel Relocked",
                description=f"{self.channel.mention} has been locked again.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Relock Failed",
                description=f"Could not relock channel: `{str(e)}`",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)


class UnlockdownCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def clear_database_lockdown(self, channel_id: int):
        """Removes the lockdown entry from SQLite database."""
        try:
            async with aiosqlite.connect(DB_FILE) as db:
                await db.execute("DELETE FROM active_lockdowns WHERE channel_id = ?", (channel_id,))
                await db.commit()
        except Exception:
            pass

    async def unlock_channel_logic(
        self,
        guild: discord.Guild,
        channel: discord.TextChannel,
        moderator: discord.Member,
        reason: str
    ):
        """Helper logic to reset @everyone permissions and notify the channel."""
        everyone_role = guild.default_role
        current_overwrite = channel.overwrites_for(everyone_role)

        # Reset permissions to default (None allows channel default inheritance)
        current_overwrite.send_messages = None
        current_overwrite.send_messages_in_threads = None
        
        await channel.set_permissions(
            everyone_role,
            overwrite=current_overwrite,
            reason=f"Unlocked by {moderator} | Reason: {reason}"
        )

        await self.clear_database_lockdown(channel.id)

        # Public Channel Notification
        announcement = discord.Embed(
            title="🔓 Channel Unlocked",
            description="The channel lockdown has ended. Standard chatting permissions have been fully restored.",
            color=discord.Color.green()
        )
        announcement.add_field(name="Reason", value=f"```\n{reason}\n```", inline=False)
        announcement.set_footer(text=f"Unlocked by {moderator}", icon_url=moderator.display_avatar.url)
        announcement.timestamp = discord.utils.utcnow()

        try:
            await channel.send(embed=announcement)
        except Exception:
            pass

    # ==========================================
    # SLASH COMMAND: /unlockdown
    # ==========================================
    @app_commands.command(
        name="unlockdown",
        description="Unlock a locked channel to restore chatting permissions for @everyone."
    )
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.bot_has_permissions(manage_channels=True)
    @app_commands.describe(
        channel="The channel to unlock (Defaults to current channel)",
        reason="Reason for unlocking the channel"
    )
    async def unlockdown_command(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
        reason: str = "No reason provided"
    ):
        target_channel = channel or interaction.channel
        guild = interaction.guild
        moderator = interaction.user

        everyone_role = guild.default_role
        current_overwrite = target_channel.overwrites_for(everyone_role)

        # Check if already unlocked
        if current_overwrite.send_messages is None or current_overwrite.send_messages is True:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Channel Not Locked",
                description=f"{target_channel.mention} is not currently in lockdown mode.",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        try:
            await self.unlock_channel_logic(
                guild=guild,
                channel=target_channel,
                moderator=moderator,
                reason=reason
            )
        except Exception as e:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Unlock Failed",
                description=f"An error occurred while unlocking {target_channel.mention}: `{str(e)}`",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # Moderator Confirmation Response
        server_embed = discord.Embed(
            title=f"{EMOJI_TICK} Channel Unlocked Successfully",
            description=f"Successfully restored message permissions for {target_channel.mention}.",
            color=discord.Color.green()
        )
        server_embed.add_field(name="Target Channel", value=target_channel.mention, inline=True)
        server_embed.add_field(name="Moderator", value=moderator.mention, inline=True)
        server_embed.add_field(name="Reason", value=f"```\n{reason}\n```", inline=False)
        server_embed.set_footer(text=f"Channel ID: {target_channel.id}", icon_url=self.bot.user.display_avatar.url)
        server_embed.timestamp = discord.utils.utcnow()

        view = UnlockdownControlView(self, target_channel, moderator)

        if interaction.channel.id == target_channel.id:
            await interaction.response.send_message(embed=server_embed, view=view, ephemeral=True)
        else:
            await interaction.response.send_message(embed=server_embed, view=view)

    # ==========================================
    # SLASH COMMAND: /unlockdown-category
    # ==========================================
    @app_commands.command(
        name="unlockdown-category",
        description="Unlock all text channels within a specific category."
    )
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.bot_has_permissions(manage_channels=True)
    @app_commands.describe(
        category="The channel category to unlock",
        reason="Reason for category unlock"
    )
    async def unlockdown_category_command(
        self,
        interaction: discord.Interaction,
        category: discord.CategoryChannel,
        reason: str = "Category lockdown lifted"
    ):
        guild = interaction.guild
        everyone_role = guild.default_role
        await interaction.response.defer()

        unlocked_count = 0
        for ch in category.text_channels:
            overwrite = ch.overwrites_for(everyone_role)
            if overwrite.send_messages is False:
                try:
                    await self.unlock_channel_logic(guild, ch, interaction.user, reason)
                    unlocked_count += 1
                except Exception:
                    pass

        embed = discord.Embed(
            title=f"{EMOJI_TICK} Category Unlocked",
            description=f"Successfully unlocked **{unlocked_count}** text channels inside **{category.name}**.",
            color=discord.Color.green()
        )
        embed.add_field(name="Category", value=category.name, inline=True)
        embed.add_field(name="Moderator", value=interaction.user.mention, inline=True)
        embed.add_field(name="Reason", value=f"```\n{reason}\n```", inline=False)
        embed.set_footer(text=f"Category ID: {category.id}", icon_url=self.bot.user.display_avatar.url)
        embed.timestamp = discord.utils.utcnow()

        await interaction.followup.send(embed=embed)

    # ==========================================
    # SLASH COMMAND: /unlockdown-server
    # ==========================================
    @app_commands.command(
        name="unlockdown-server",
        description="EMERGENCY OVERRIDE: Lift lockdown from ALL text channels across the entire server."
    )
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.bot_has_permissions(manage_channels=True)
    @app_commands.describe(reason="Reason for restoring full server messaging")
    async def unlockdown_server_command(
        self, 
        interaction: discord.Interaction, 
        reason: str = "Server Emergency Resolved"
    ):
        guild = interaction.guild
        await interaction.response.defer()

        everyone_role = guild.default_role
        unlocked_channels: List[discord.TextChannel] = []

        for ch in guild.text_channels:
            overwrite = ch.overwrites_for(everyone_role)
            if overwrite.send_messages is False:
                try:
                    overwrite.send_messages = None
                    overwrite.send_messages_in_threads = None
                    await ch.set_permissions(
                        everyone_role,
                        overwrite=overwrite,
                        reason=f"Server Unlockdown by {interaction.user} | Reason: {reason}"
                    )
                    unlocked_channels.append(ch)
                    await self.clear_database_lockdown(ch.id)
                except Exception:
                    pass

        embed = discord.Embed(
            title=f"{EMOJI_TICK} MASS SERVER UNLOCKDOWN COMPLETED",
            description=f"Successfully unlocked **{len(unlocked_channels)}** text channels across **{guild.name}**.",
            color=discord.Color.green()
        )
        embed.add_field(name="Moderator", value=interaction.user.mention, inline=True)
        embed.add_field(name="Reason", value=f"```\n{reason}\n```", inline=False)
        embed.set_footer(text="All normal chat permissions have been restored.", icon_url=self.bot.user.display_avatar.url)
        embed.timestamp = discord.utils.utcnow()

        await interaction.followup.send(embed=embed)

    # ==========================================
    # ERROR HANDLING
    # ==========================================
    @unlockdown_command.error
    @unlockdown_category_command.error
    @unlockdown_server_command.error
    async def unlockdown_error_handler(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError
    ):
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
    await bot.add_cog(UnlockdownCog(bot))
      
