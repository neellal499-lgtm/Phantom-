import discord
from discord import app_commands
from discord.ext import commands

# Custom Emoji Constants
EMOJI_TICK = "<a:Tick:1536982741537656832>"
EMOJI_CROSS = "<:Cross:1536982744008106055>"

class UnbanCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ==========================================
    # SLASH COMMAND: /unban
    # ==========================================
    @app_commands.command(name="unban", description="Unban a user from the server using their User ID.")
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.bot_has_permissions(ban_members=True)
    @app_commands.describe(
        user_id="The Discord User ID of the banned user",
        reason="The reason for unbanning this user"
    )
    async def unban_command(
        self, 
        interaction: discord.Interaction, 
        user_id: str, 
        reason: str
    ):
        guild = interaction.guild
        moderator = interaction.user

        # ----------------------------------------------------
        # ID VALIDATION
        # ----------------------------------------------------
        try:
            target_id = int(user_id.strip())
        except ValueError:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Invalid User ID",
                description="Please provide a valid numerical Discord User ID (e.g., `123456789012345678`).",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # ----------------------------------------------------
        # CHECK IF USER IS ACTUALLY BANNED
        # ----------------------------------------------------
        banned_entry = None
        async for ban_entry in guild.bans():
            if ban_entry.user.id == target_id:
                banned_entry = ban_entry
                break

        if not banned_entry:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} User Not Banned",
                description=f"No active ban record was found for User ID `{target_id}` in this server.",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        target_user = banned_entry.user

        # ----------------------------------------------------
        # EXECUTE UNBAN
        # ----------------------------------------------------
        try:
            await guild.unban(target_user, reason=f"Unbanned by {moderator} | Reason: {reason}")
        except Exception as e:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Unban Failed",
                description=f"An error occurred while trying to unban `{target_user}`: `{str(e)}`",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # ----------------------------------------------------
        # SERVER CHANNEL CONFIRMATION EMBED
        # ----------------------------------------------------
        server_embed = discord.Embed(
            title=f"{EMOJI_TICK} User Unbanned Successfully",
            description=f"**{target_user.name}** (`{target_user.id}`) has been unbanned from the server.",
            color=discord.Color.green()
        )
        server_embed.set_thumbnail(url=target_user.display_avatar.url)
        server_embed.add_field(name="Unbanned User", value=f"{target_user.mention} (`{target_user.id}`)", inline=True)
        server_embed.add_field(name="Moderator", value=f"{moderator.mention}", inline=True)
        server_embed.add_field(name="Reason", value=f"```\n{reason}\n```", inline=False)
        server_embed.set_footer(text=f"Target ID: {target_user.id}", icon_url=self.bot.user.display_avatar.url)
        server_embed.timestamp = discord.utils.utcnow()

        await interaction.response.send_message(embed=server_embed)

    # ==========================================
    # ERROR HANDLING: Missing Permissions & Missing Arguments
    # ==========================================
    @unban_command.error
    async def unban_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
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
            embed.set_footer(text="Usage: /unban user_id:<ID> reason:<text>")
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
    await bot.add_cog(UnbanCog(bot))
  
