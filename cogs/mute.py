import re
from datetime import timedelta
import discord
from discord import app_commands
from discord.ext import commands

# Custom Emoji Constants
EMOJI_TICK = "<a:Tick:1536982741537656832>"
EMOJI_CROSS = "<:Cross:1536982744008106055>"

def parse_duration(duration_str: str) -> timedelta | None:
    """Parses duration strings like '10m', '2h', '1d', '30s' into standard timedelta objects."""
    match = re.match(r"^(\d+)\s*([sSmMhHdD])$", duration_str.strip())
    if not match:
        return None

    value, unit = int(match.group(1)), match.group(2).lower()
    if unit == 's':
        return timedelta(seconds=value)
    elif unit == 'm':
        return timedelta(minutes=value)
    elif unit == 'h':
        return timedelta(hours=value)
    elif unit == 'd':
        return timedelta(days=value)
    return None

class MuteCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ==========================================
    # SLASH COMMAND: /mute
    # ==========================================
    @app_commands.command(name="mute", description="Timeout/Mute a member in the server.")
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.bot_has_permissions(moderate_members=True)
    @app_commands.describe(
        user="The member you want to mute",
        duration="Mute duration (e.g., 10m, 1h, 1d - max 28d)",
        reason="The reason for muting this member"
    )
    async def mute_command(
        self, 
        interaction: discord.Interaction, 
        user: discord.Member, 
        duration: str,
        reason: str
    ):
        guild = interaction.guild
        moderator = interaction.user

        # ----------------------------------------------------
        # DURATION PARSING & VALIDATION
        # ----------------------------------------------------
        delta = parse_duration(duration)
        if not delta:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Invalid Duration Format",
                description="Please use a valid time format:\n• `10m` = 10 Minutes\n• `2h` = 2 Hours\n• `1d` = 1 Day",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        if delta > timedelta(days=28):
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Duration Limit Exceeded",
                description="Discord timeouts cannot exceed **28 days**.",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # ----------------------------------------------------
        # HIERARCHY CHECKS
        # ----------------------------------------------------
        if user.id == moderator.id:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Action Prohibited",
                description="You cannot mute yourself.",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        if user.id == self.bot.user.id:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Action Prohibited",
                description="I cannot mute myself.",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        if user.top_role >= moderator.top_role and moderator.id != guild.owner_id:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Hierarchy Error",
                description=f"You cannot mute {user.mention} because their highest role ({user.top_role.mention}) is equal to or higher than yours.",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        if user.top_role >= guild.me.top_role:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Hierarchy Error",
                description=f"I cannot mute {user.mention} because their highest role ({user.top_role.mention}) is equal to or higher than my top role.",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # ----------------------------------------------------
        # DIRECT MESSAGE NOTIFICATION
        # ----------------------------------------------------
        dm_sent = False
        dm_embed = discord.Embed(
            title=f"{EMOJI_CROSS} You have been muted",
            description=f"You received a timeout in **{guild.name}**.",
            color=discord.Color.red()
        )
        dm_embed.add_field(name="Duration", value=f"`{duration}`", inline=True)
        dm_embed.add_field(name="Moderator", value=f"{moderator} (`{moderator.id}`)", inline=True)
        dm_embed.add_field(name="Reason", value=f"```\n{reason}\n```", inline=False)
        if guild.icon:
            dm_embed.set_thumbnail(url=guild.icon.url)
        dm_embed.set_footer(text="Please review server guidelines during your timeout.")
        dm_embed.timestamp = discord.utils.utcnow()

        try:
            await user.send(embed=dm_embed)
            dm_sent = True
        except (discord.Forbidden, discord.HTTPException):
            dm_sent = False

        # ----------------------------------------------------
        # EXECUTE TIMEOUT/MUTE
        # ----------------------------------------------------
        try:
            await user.timeout(delta, reason=f"Muted by {moderator} | Reason: {reason}")
        except Exception as e:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Mute Failed",
                description=f"An error occurred while muting {user.mention}: `{str(e)}`",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # ----------------------------------------------------
        # SERVER CHANNEL CONFIRMATION EMBED
        # ----------------------------------------------------
        server_embed = discord.Embed(
            title=f"{EMOJI_TICK} Member Muted Successfully",
            description=f"{user.mention} has been muted.",
            color=discord.Color.green()
        )
        server_embed.set_thumbnail(url=user.display_avatar.url)
        server_embed.add_field(name="Muted Member", value=f"{user.name} (`{user.id}`)", inline=True)
        server_embed.add_field(name="Duration", value=f"`{duration}`", inline=True)
        server_embed.add_field(name="DM Notification", value=f"`{'Sent' if dm_sent else 'Failed (DMs Closed)'}`", inline=True)
        server_embed.add_field(name="Moderator", value=f"{moderator.mention}", inline=True)
        server_embed.add_field(name="Reason", value=f"```\n{reason}\n```", inline=False)
        server_embed.set_footer(text=f"Target ID: {user.id}", icon_url=self.bot.user.display_avatar.url)
        server_embed.timestamp = discord.utils.utcnow()

        await interaction.response.send_message(embed=server_embed)

    # ==========================================
    # ERROR HANDLING: Permissions & Arguments
    # ==========================================
    @mute_command.error
    async def mute_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
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
            embed.set_footer(text="Usage: /mute user:<member> duration:<10m/1h> reason:<text>")
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        else:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Unexpected Error",
                description=f"An error occurred: `{str(error)}`",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(MuteCog(bot))

