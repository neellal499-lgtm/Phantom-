import asyncio
from datetime import datetime, timedelta
import re
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands, tasks

# Custom Emoji Constants
EMOJI_TICK = "<a:Tick:1536982741537656832>"
EMOJI_CROSS = "<:Cross:1536982744008106055>"


def parse_duration(duration_str: str) -> Optional[timedelta]:
    """Parses time strings like '10m', '2h', '1d' into timedelta objects."""
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


class AddRoleCog(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Format: list of dicts {"guild_id": int, "user_id": int, "role_id": int, "expiry": datetime}
        self.temp_roles = []
        self.check_temp_roles.start()

    def cog_unload(self):
        self.check_temp_roles.cancel()

    # ==========================================
    # BACKGROUND TASK: TEMP ROLE EXPIRATION
    # ==========================================
    @tasks.loop(seconds=10)
    async def check_temp_roles(self):
        """Monitors temporary roles and automatically revokes them when expired."""
        now = discord.utils.utcnow()
        to_remove = []

        for entry in self.temp_roles:
            if now >= entry["expiry"]:
                guild = self.bot.get_guild(entry["guild_id"])
                if guild:
                    member = guild.get_member(entry["user_id"])
                    role = guild.get_role(entry["role_id"])

                    if member and role and role in member.roles:
                        try:
                            await member.remove_roles(
                                role, reason="Temporary role duration expired."
                            )
                            # Notify member in DM if possible
                            dm_embed = discord.Embed(
                                title=f"{EMOJI_CROSS} Temporary Role Expired",
                                description=f"Your temporary role **{role.name}** in **{guild.name}** has expired and was automatically removed.",
                                color=discord.Color.orange(),
                            )
                            dm_embed.timestamp = now
                            await member.send(embed=dm_embed)
                        except (discord.Forbidden, discord.HTTPException):
                            pass
                to_remove.append(entry)

        for entry in to_remove:
            self.temp_roles.remove(entry)

    @check_temp_roles.before_loop
    async def before_check_temp_roles(self):
        await self.bot.wait_until_ready()

    # ==========================================
    # SLASH COMMAND: /addrole
    # ==========================================
    @app_commands.command(
        name="addrole",
        description="Assign a primary role (and an optional second role) to a server member.",
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    @app_commands.bot_has_permissions(manage_roles=True)
    @app_commands.describe(
        user="The member to assign the role to",
        role="The primary role you want to add",
        second_role="Optional: A secondary role to add simultaneously",
        duration="Optional: Make this temporary (e.g., 10m, 2h, 1d)",
        reason="Optional: Reason for giving this role",
    )
    async def addrole_command(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        role: discord.Role,
        second_role: Optional[discord.Role] = None,
        duration: Optional[str] = None,
        reason: str = "No reason provided",
    ):
        guild = interaction.guild
        moderator = interaction.user
        roles_to_add = [role]
        if second_role and second_role != role:
            roles_to_add.append(second_role)

        # Parse duration if provided
        expiry_time = None
        duration_delta = None
        if duration:
            duration_delta = parse_duration(duration)
            if not duration_delta:
                embed = discord.Embed(
                    title=f"{EMOJI_CROSS} Invalid Duration Format",
                    description=(
                        "Please provide a valid time unit:\n"
                        "• `10m` = 10 Minutes\n"
                        "• `2h` = 2 Hours\n"
                        "• `1d` = 1 Day"
                    ),
                    color=discord.Color.red(),
                )
                return await interaction.response.send_message(
                    embed=embed, ephemeral=True
                )
            expiry_time = discord.utils.utcnow() + duration_delta

        # ----------------------------------------------------
        # HIERARCHY & VALIDATION CHECKS
        # ----------------------------------------------------
        for r in roles_to_add:
            # 1. Check if user already has role
            if r in user.roles:
                embed = discord.Embed(
                    title=f"{EMOJI_CROSS} Role Already Assigned",
                    description=f"{user.mention} already has the {r.mention} role.",
                    color=discord.Color.red(),
                )
                return await interaction.response.send_message(
                    embed=embed, ephemeral=True
                )

            # 2. Check for integrated/managed roles
            if r.is_integration() or r.is_bot_managed():
                embed = discord.Embed(
                    title=f"{EMOJI_CROSS} Managed Role Error",
                    description=f"The role {r.mention} is managed by an integration/bot and cannot be manually assigned.",
                    color=discord.Color.red(),
                )
                return await interaction.response.send_message(
                    embed=embed, ephemeral=True
                )

            # 3. Check moderator hierarchy
            if r >= moderator.top_role and moderator.id != guild.owner_id:
                embed = discord.Embed(
                    title=f"{EMOJI_CROSS} Hierarchy Error",
                    description=f"You cannot assign {r.mention} because it is equal to or higher than your highest role ({moderator.top_role.mention}).",
                    color=discord.Color.red(),
                )
                return await interaction.response.send_message(
                    embed=embed, ephemeral=True
                )

            # 4. Check bot hierarchy
            if r >= guild.me.top_role:
                embed = discord.Embed(
                    title=f"{EMOJI_CROSS} Hierarchy Error",
                    description=f"I cannot assign {r.mention} because it is equal to or higher than my top role ({guild.me.top_role.mention}).",
                    color=discord.Color.red(),
                )
                return await interaction.response.send_message(
                    embed=embed, ephemeral=True
                )

        # ----------------------------------------------------
        # EXECUTE ROLE ADDITION
        # ----------------------------------------------------
        audit_reason = f"Role(s) added by {moderator} ({moderator.id}) | Reason: {reason}"
        try:
            await user.add_roles(*roles_to_add, reason=audit_reason)
        except Exception as e:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Role Assignment Failed",
                description=f"An error occurred while updating roles for {user.mention}: `{str(e)}`",
                color=discord.Color.red(),
            )
            return await interaction.response.send_message(
                embed=embed, ephemeral=True
            )

        # Track temporary roles if duration was specified
        if expiry_time:
            for r in roles_to_add:
                self.temp_roles.append(
                    {
                        "guild_id": guild.id,
                        "user_id": user.id,
                        "role_id": r.id,
                        "expiry": expiry_time,
                    }
                )

        # ----------------------------------------------------
        # DIRECT MESSAGE NOTIFICATION
        # ----------------------------------------------------
        dm_sent = False
        roles_text = ", ".join([r.mention for r in roles_to_add])
        dm_embed = discord.Embed(
            title=f"{EMOJI_TICK} Role Updated",
            description=f"You were granted the following role(s) in **{guild.name}**:",
            color=role.color if role.color.value != 0 else discord.Color.blue(),
        )
        dm_embed.add_field(name="Role(s)", value=roles_text, inline=False)
        if duration:
            dm_embed.add_field(
                name="Duration", value=f"`{duration}` (Temporary)", inline=True
            )
        dm_embed.add_field(
            name="Moderator", value=f"{moderator}", inline=True
        )
        dm_embed.add_field(
            name="Reason", value=f"```\n{reason}\n```", inline=False
        )
        dm_embed.set_thumbnail(
            url=guild.icon.url if guild.icon else user.display_avatar.url
        )
        dm_embed.timestamp = discord.utils.utcnow()

        try:
            await user.send(embed=dm_embed)
            dm_sent = True
        except (discord.Forbidden, discord.HTTPException):
            dm_sent = False

        # ----------------------------------------------------
        # SERVER CHANNEL CONFIRMATION EMBED
        # ----------------------------------------------------
        embed_color = (
            role.color if role.color.value != 0 else discord.Color.green()
        )
        server_embed = discord.Embed(
            title=f"{EMOJI_TICK} Role(s) Assigned Successfully",
            description=f"Successfully updated roles for {user.mention}.",
            color=embed_color,
        )
        server_embed.set_thumbnail(url=user.display_avatar.url)
        server_embed.add_field(
            name="Target Member",
            value=f"{user.name} (`{user.id}`)",
            inline=True,
        )
        server_embed.add_field(
            name="Assigned Role(s)", value=roles_text, inline=True
        )
        server_embed.add_field(
            name="DM Status",
            value=f"`{'Sent' if dm_sent else 'Failed (DMs Closed)'}`",
            inline=True,
        )

        if duration:
            server_embed.add_field(
                name="Duration", value=f"`{duration}`", inline=True
            )
            server_embed.add_field(
                name="Expires At",
                value=f"<t:{int(expiry_time.timestamp())}:R>",
                inline=True,
            )

        server_embed.add_field(
            name="Moderator", value=f"{moderator.mention}", inline=False
        )
        server_embed.add_field(
            name="Reason", value=f"```\n{reason}\n```", inline=False
        )
        server_embed.set_footer(
            text=f"Target ID: {user.id}",
            icon_url=self.bot.user.display_avatar.url,
        )
        server_embed.timestamp = discord.utils.utcnow()

        await interaction.response.send_message(embed=server_embed)

    # ==========================================
    # ERROR HANDLING: Permissions & Arguments
    # ==========================================
    @addrole_command.error
    async def addrole_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ):
        if isinstance(error, app_commands.MissingPermissions):
            missing_perms = ", ".join(
                [f"`{perm}`" for perm in error.missing_permissions]
            )
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Permission Denied",
                description=f"{interaction.user.mention}, you lack permission(s): {missing_perms}",
                color=discord.Color.red(),
            )
            embed.set_footer(text="Required Permission: MANAGE_ROLES")
            return await interaction.response.send_message(
                embed=embed, ephemeral=True
            )

        elif isinstance(error, app_commands.BotMissingPermissions):
            missing_perms = ", ".join(
                [f"`{perm}`" for perm in error.missing_permissions]
            )
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Bot Permission Required",
                description=f"I am missing required permission(s): {missing_perms}",
                color=discord.Color.red(),
            )
            embed.set_footer(
                text="Please grant the bot Manage Roles permission."
            )
            return await interaction.response.send_message(
                embed=embed, ephemeral=True
            )

        elif isinstance(error, app_commands.MissingRequiredArgument):
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Missing Parameter",
                description=f"{interaction.user.mention}, missing argument: `{error.param.name}`.",
                color=discord.Color.red(),
            )
            embed.set_footer(
                text="Usage: /addrole user:<member> role:<role> [second_role:<role>] [duration:<time>] [reason:<text>]"
            )
            return await interaction.response.send_message(
                embed=embed, ephemeral=True
            )

        else:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Unexpected Error",
                description=f"An error occurred: `{str(error)}`",
                color=discord.Color.red(),
            )
            return await interaction.response.send_message(
                embed=embed, ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(AddRoleCog(bot))
  
