import discord
from discord import app_commands
from discord.ext import commands

# Custom Emoji Constants
EMOJI_TICK = "<a:Tick:1536982741537656832>"
EMOJI_CROSS = "<:Cross:1536982744008106055>"

class BanCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ==========================================
    # SLASH COMMAND: /ban
    # ==========================================
    @app_commands.command(name="ban", description="Ban a member from the server.")
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.bot_has_permissions(ban_members=True)
    @app_commands.describe(
        user="The member you want to ban",
        reason="The reason for banning this member"
    )
    async def ban_command(
        self, 
        interaction: discord.Interaction, 
        user: discord.Member, 
        reason: str
    ):
        guild = interaction.guild
        moderator = interaction.user

        # ----------------------------------------------------
        # HIERARCHY CHECKS
        # ----------------------------------------------------
        # 1. Cannot ban yourself
        if user.id == moderator.id:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Action Prohibited",
                description="You cannot ban yourself from the server.",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # 2. Cannot ban the bot
        if user.id == self.bot.user.id:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Action Prohibited",
                description="I cannot ban myself from the server.",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # 3. Check if target's top role is higher than or equal to moderator's top role
        if user.top_role >= moderator.top_role and moderator.id != guild.owner_id:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Hierarchy Error",
                description=f"You cannot ban {user.mention} because their highest role ({user.top_role.mention}) is higher than or equal to yours ({moderator.top_role.mention}).",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # 4. Check if target's top role is higher than or equal to bot's top role
        if user.top_role >= guild.me.top_role:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Hierarchy Error",
                description=f"I cannot ban {user.mention} because their highest role ({user.top_role.mention}) is higher than or equal to my highest role ({guild.me.top_role.mention}).",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # ----------------------------------------------------
        # SEND DM TO USER BEFORE BANNING
        # ----------------------------------------------------
        dm_sent = False
        dm_embed = discord.Embed(
            title=f"{EMOJI_CROSS} You have been banned",
            description=f"You were permanently banned from **{guild.name}**.",
            color=discord.Color.dark_red()
        )
        dm_embed.add_field(name="Reason", value=f"```\n{reason}\n```", inline=False)
        dm_embed.add_field(name="Moderator", value=f"{moderator} (`{moderator.id}`)", inline=True)
        if guild.icon:
            dm_embed.set_thumbnail(url=guild.icon.url)
        dm_embed.set_footer(text="If you believe this was a mistake, contact the server administration.")
        dm_embed.timestamp = discord.utils.utcnow()

        try:
            await user.send(embed=dm_embed)
            dm_sent = True
        except (discord.Forbidden, discord.HTTPException):
            dm_sent = False

        # ----------------------------------------------------
        # EXECUTE BAN
        # ----------------------------------------------------
        try:
            await guild.ban(user, reason=f"Banned by {moderator} | Reason: {reason}")
        except Exception as e:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Ban Failed",
                description=f"An error occurred while trying to ban {user.mention}: `{str(e)}`",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # ----------------------------------------------------
        # SERVER CHANNEL CONFIRMATION EMBED
        # ----------------------------------------------------
        server_embed = discord.Embed(
            title=f"{EMOJI_TICK} Member Banned Successfully",
            description=f"{user.mention} has been permanently banned from the server.",
            color=discord.Color.green()
        )
        server_embed.set_thumbnail(url=user.display_avatar.url)
        server_embed.add_field(name="Banned User", value=f"{user.name} (`{user.id}`)", inline=True)
        server_embed.add_field(name="Moderator", value=f"{moderator.mention}", inline=True)
        server_embed.add_field(name="DM Notification", value=f"`{'Sent' if dm_sent else 'Failed (DMs Closed)'}`", inline=True)
        server_embed.add_field(name="Reason", value=f"```\n{reason}\n```", inline=False)
        server_embed.set_footer(text=f"Target ID: {user.id}", icon_url=self.bot.user.display_avatar.url)
        server_embed.timestamp = discord.utils.utcnow()

        await interaction.response.send_message(embed=server_embed)

    # ==========================================
    # ERROR HANDLING: Missing Permissions & Missing Arguments
    # ==========================================
    @ban_command.error
    async def ban_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        # 1. Missing Permissions (User or Bot)
        if isinstance(error, app_commands.MissingPermissions):
            missing_perms = ", ".join([f"`{perm}`" for perm in error.missing_permissions])
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Permission Denied",
                description=f"{interaction.user.mention}, you lack the required permission(s) to use this command: {missing_perms}",
                color=discord.Color.red()
            )
            embed.set_footer(text="Required Permission: BAN_MEMBERS")
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        elif isinstance(error, app_commands.BotMissingPermissions):
            missing_perms = ", ".join([f"`{perm}`" for perm in error.missing_permissions])
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Bot Permission Required",
                description=f"I cannot execute this command because I am missing the required permission(s): {missing_perms}",
                color=discord.Color.red()
            )
            embed.set_footer(text="Please grant the bot Ban Members permission in Server Settings.")
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # 2. Missing Required Argument
        elif isinstance(error, app_commands.MissingRequiredArgument):
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Missing Parameter",
                description=f"{interaction.user.mention}, you missed a required argument: `{error.param.name}`.",
                color=discord.Color.red()
            )
            embed.set_footer(text="Usage: /ban user:<@member> reason:<text>")
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # Catch-all for other unexpected errors
        else:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Unexpected Error",
                description=f"An error occurred: `{str(error)}`",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(BanCog(bot))
      
