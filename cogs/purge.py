from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands

# Custom Emoji Constants
EMOJI_TICK = "<a:Tick:1536982741537656832>"
EMOJI_CROSS = "<:Cross:1536982744008106055>"

class PurgeCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ==========================================
    # SLASH COMMAND: /purge
    # ==========================================
    @app_commands.command(name="purge", description="Delete a specified number of messages from the channel.")
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.bot_has_permissions(manage_messages=True)
    @app_commands.describe(
        message="Number of messages to scan/delete (max 200)",
        target_user="Optional: Only delete messages from this specific user"
    )
    async def purge_command(
        self, 
        interaction: discord.Interaction, 
        message: int, 
        target_user: Optional[discord.Member] = None
    ):
        # ----------------------------------------------------
        # VALIDATE MESSAGE LIMIT (MAX 200)
        # ----------------------------------------------------
        if message <= 0:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Invalid Amount",
                description="Please specify a message count greater than `0`.",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        if message > 200:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Limit Exceeded",
                description="You can only purge a maximum of **200 messages** at a time.",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # Defer response ephemerally to prevent interaction timeouts during bulk deletion
        await interaction.response.defer(ephemeral=True)

        # Build check function if a target user is provided
        check_func = (lambda m: m.author.id == target_user.id) if target_user else None

        # ----------------------------------------------------
        # EXECUTE PURGE
        # ----------------------------------------------------
        try:
            deleted = await interaction.channel.purge(limit=message, check=check_func)
            deleted_count = len(deleted)
        except Exception as e:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Purge Failed",
                description=f"An error occurred while purging messages: `{str(e)}`",
                color=discord.Color.red()
            )
            return await interaction.followup.send(embed=embed, ephemeral=True)

        # ----------------------------------------------------
        # CONFIRMATION EMBED
        # ----------------------------------------------------
        server_embed = discord.Embed(
            title=f"{EMOJI_TICK} Purge Successful",
            description=f"Successfully deleted **{deleted_count}** message(s).",
            color=discord.Color.green()
        )
        if target_user:
            server_embed.add_field(name="Filtered User", value=f"{target_user.mention} (`{target_user.id}`)", inline=False)
        server_embed.add_field(name="Moderator", value=f"{interaction.user.mention}", inline=True)
        server_embed.add_field(name="Channel", value=f"{interaction.channel.mention}", inline=True)
        server_embed.set_footer(text=f"Action performed by {interaction.user}", icon_url=interaction.user.display_avatar.url)
        server_embed.timestamp = discord.utils.utcnow()

        await interaction.followup.send(embed=server_embed, ephemeral=True)

    # ==========================================
    # ERROR HANDLING: Permissions & Arguments
    # ==========================================
    @purge_command.error
    async def purge_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            missing_perms = ", ".join([f"`{perm}`" for perm in error.missing_permissions])
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Permission Denied",
                description=f"{interaction.user.mention}, you lack permission(s): {missing_perms}",
                color=discord.Color.red()
            )
            embed.set_footer(text="Required Permission: MANAGE_MESSAGES")
            
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
            embed.set_footer(text="Please grant the bot Manage Messages permission.")
            
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)

        elif isinstance(error, app_commands.MissingRequiredArgument):
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Missing Parameter",
                description=f"{interaction.user.mention}, missing argument: `{error.param.name}`.",
                color=discord.Color.red()
            )
            embed.set_footer(text="Usage: /purge message:<count> [target-user:<member>]")
            
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
    await bot.add_cog(PurgeCog(bot))
  
