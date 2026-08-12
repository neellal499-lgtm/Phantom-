import discord
from discord import app_commands
from discord.ext import commands

# Custom Emoji Constants
EMOJI_TICK = "<a:Tick:1536982741537656832>"
EMOJI_CROSS = "<:Cross:1536982744008106055>"

class UnmuteCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ==========================================
    # SLASH COMMAND: /unmute
    # ==========================================
    @app_commands.command(name="unmute", description="Remove timeout/mute from a member in the server.")
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.bot_has_permissions(moderate_members=True)
    @app_commands.describe(
        user="The member you want to unmute",
        reason="The reason for unmuting this member"
    )
    async def unmute_command(
        self, 
        interaction: discord.Interaction, 
        user: discord.Member, 
        reason: str
    ):
        guild = interaction.guild
        moderator = interaction.user

        # ----------------------------------------------------
        # CHECK IF MEMBER IS ACTUALLY MUTED/TIMED OUT
        # ----------------------------------------------------
        if not user.is_timed_out():
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Member Not Muted",
                description=f"{user.mention} does not currently have an active timeout.",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # ----------------------------------------------------
        # HIERARCHY CHECKS
        # ----------------------------------------------------
        if user.top_role >= moderator.top_role and moderator.id != guild.owner_id:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Hierarchy Error",
                description=f"You cannot unmute {user.mention} because their highest role ({user.top_role.mention}) is equal to or higher than yours.",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        if user.top_role >= guild.me.top_role:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Hierarchy Error",
                description=f"I cannot unmute {user.mention} because their highest role ({user.top_role.mention}) is equal to or higher than my top role.",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # ----------------------------------------------------
        # DIRECT MESSAGE NOTIFICATION
        # ----------------------------------------------------
        dm_sent = False
        dm_embed = discord.Embed(
            title=f"{EMOJI_TICK} You have been unmuted",
            description=f"Your timeout in **{guild.name}** has been removed.",
            color=discord.Color.green()
        )
        dm_embed.add_field(name="Moderator", value=f"{moderator} (`{moderator.id}`)", inline=True)
        dm_embed.add_field(name="Reason", value=f"```\n{reason}\n```", inline=False)
        if guild.icon:
            dm_embed.set_thumbnail(url=guild.icon.url)
        dm_embed.set_footer(text="You are free to text in the server again.")
        dm_embed.timestamp = discord.utils.utcnow()

        try:
            await user.send(embed=dm_embed)
            dm_sent = True
        except (discord.Forbidden, discord.HTTPException):
            dm_sent = False

        # ----------------------------------------------------
        # EXECUTE UNMUTE (REMOVE TIMEOUT)
        # ----------------------------------------------------
        try:
            await user.timeout(None, reason=f"Unmuted by {moderator} | Reason: {reason}")
        except Exception as e:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Unmute Failed",
                description=f"An error occurred while unmuting {user.mention}: `{str(e)}`",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # ----------------------------------------------------
        # SERVER CHANNEL CONFIRMATION EMBED
        # ----------------------------------------------------
        server_embed = discord.Embed(
            title=f"{EMOJI_TICK} Member Unmuted Successfully",
            description=f"{user.mention} has been unmuted.",
            color=discord.Color.green()
        )
        server_embed.set_thumbnail(url=user.display_avatar.url)
        server_embed.add_field(name="Unmuted Member", value=f"{user.name} (`{user.id}`)", inline=True)
        server_embed.add_field(name="DM Notification", value=f"`{'Sent' if dm_sent else 'Failed (DMs Closed)'}`", inline=True)
        server_embed.add_field(name="Moderator", value=f"{moderator.mention}", inline=True)
        server_embed.add_field(name="Reason", value=f"```\n{reason}\n```", inline=False)
        server_embed.set_footer(text=f"Target ID: {user.id}", icon_url=self.bot.user.display_avatar.url)
        server_embed.timestamp = discord.utils.utcnow()

        await interaction.response.send_message(embed=server_embed)

    # ==========================================
    # ERROR HANDLING: Permissions & Arguments
    # ==========================================
    @unmute_command.error
    async def unmute_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            missing_perms = ", ".join([f"`{perm}`" for perm in error.missing_permissions])
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Permission Denied",
                description=f"{interaction.user.mention}, you lack permission(s): {missing_perms}",
                color=discord.Color.red()
            )
            embed.set_footer(text="Required Permission: MODERATE_MEMBERS")
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        elif isinstance(error, app_commands.BotMissingPermissions):
            missing_perms = ", ".join([f"`{perm}`" for perm in error.missing_permissions])
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Bot Permission Required",
                description=f"I am missing required permission(s): {missing_perms}",
                color=discord.Color.red()
            )
            embed.set_footer(text="Please grant the bot Moderate Members permission.")
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        elif isinstance(error, app_commands.MissingRequiredArgument):
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Missing Parameter",
                description=f"{interaction.user.mention}, missing argument: `{error.param.name}`.",
                color=discord.Color.red()
            )
            embed.set_footer(text="Usage: /unmute user:<member> reason:<text>")
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        else:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Unexpected Error",
                description=f"An error occurred: `{str(error)}`",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(UnmuteCog(bot))
      
