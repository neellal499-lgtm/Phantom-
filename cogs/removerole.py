import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, List

# Custom Emoji Constants
EMOJI_TICK = "<a:Tick:1536982741537656832>"
EMOJI_CROSS = "<:Cross:1536982744008106055>"


class RoleSelectMenu(discord.ui.Select):
    """Interactive Dropdown Menu for selecting roles to remove from a user."""
    def __init__(self, target_member: discord.Member, removable_roles: List[discord.Role]):
        options = [
            discord.SelectOption(
                label=role.name,
                value=str(role.id),
                description=f"ID: {role.id}",
                emoji="🛡️"
            ) for role in removable_roles[:25]  # Discord limits dropdowns to 25 items
        ]
        super().__init__(
            placeholder=f"Select role(s) to remove from {target_member.display_name}...",
            min_values=1,
            max_values=min(len(options), 5),
            options=options
        )
        self.target_member = target_member

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        self.view.selected_role_ids = [int(val) for val in self.values]
        self.view.stop()


class RoleSelectView(discord.ui.View):
    """View container for the interactive role select dropdown."""
    def __init__(self, target_member: discord.Member, removable_roles: List[discord.Role], author: discord.Member):
        super().__init__(timeout=60)
        self.author = author
        self.selected_role_ids: List[int] = []
        self.select_menu = RoleSelectMenu(target_member, removable_roles)
        self.add_item(self.select_menu)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                f"{EMOJI_CROSS} Only the moderator who ran this command can use this menu.",
                ephemeral=True
            )
            return False
        return True


class RemoveRoleCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def get_removable_roles(self, moderator: discord.Member, target: discord.Member, bot_member: discord.Member) -> List[discord.Role]:
        """Filters target user roles that can be safely removed based on permissions and hierarchy."""
        removable = []
        for role in target.roles:
            if role.is_default():  # Skip @everyone
                continue
            if role.is_integration() or role.is_bot_managed():
                continue
            if role >= bot_member.top_role:
                continue
            if role >= moderator.top_role and moderator.id != target.guild.owner_id:
                continue
            removable.append(role)
        return removable

    # ==========================================
    # SLASH COMMAND: /removerole
    # ==========================================
    @app_commands.command(
        name="removerole",
        description="Advanced role removal utility with multi-role support, interactive menus, and mass strip."
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    @app_commands.bot_has_permissions(manage_roles=True)
    @app_commands.describe(
        user="The member to remove role(s) from",
        role="Primary role to remove (Leave empty for interactive dropdown)",
        second_role="Optional: A second role to remove simultaneously",
        third_role="Optional: A third role to remove simultaneously",
        strip_all="Optional: Set to True to strip ALL removable roles from the user",
        reason="Optional: Reason for removing these roles"
    )
    async def removerole_command(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        role: Optional[discord.Role] = None,
        second_role: Optional[discord.Role] = None,
        third_role: Optional[discord.Role] = None,
        strip_all: bool = False,
        reason: str = "No reason provided"
    ):
        guild = interaction.guild
        moderator = interaction.user
        bot_member = guild.me

        # Fetch all roles that the moderator and bot are permitted to strip from this user
        valid_removable_roles = self.get_removable_roles(moderator, user, bot_member)

        # ----------------------------------------------------
        # MODE 1: MASS STRIP ALL ROLES
        # ----------------------------------------------------
        if strip_all:
            if not valid_removable_roles:
                embed = discord.Embed(
                    title=f"{EMOJI_CROSS} No Stripable Roles Found",
                    description=f"{user.mention} has no roles that you have permission to remove.",
                    color=discord.Color.red()
                )
                return await interaction.response.send_message(embed=embed, ephemeral=True)

            audit_reason = f"Mass role strip by {moderator} ({moderator.id}) | Reason: {reason}"
            try:
                await user.remove_roles(*valid_removable_roles, reason=audit_reason)
            except Exception as e:
                embed = discord.Embed(
                    title=f"{EMOJI_CROSS} Mass Strip Failed",
                    description=f"An error occurred while stripping roles: `{str(e)}`",
                    color=discord.Color.red()
                )
                return await interaction.response.send_message(embed=embed, ephemeral=True)

            # Confirmation Embed
            roles_stripped_text = ", ".join([r.mention for r in valid_removable_roles])
            embed = discord.Embed(
                title=f"{EMOJI_TICK} All Roles Stripped Successfully",
                description=f"Removed **{len(valid_removable_roles)}** role(s) from {user.mention}.",
                color=discord.Color.green()
            )
            embed.set_thumbnail(url=user.display_avatar.url)
            embed.add_field(name="Target Member", value=f"{user.name} (`{user.id}`)", inline=True)
            embed.add_field(name="Moderator", value=f"{moderator.mention}", inline=True)
            embed.add_field(name="Stripped Roles", value=roles_stripped_text[:1024], inline=False)
            embed.add_field(name="Reason", value=f"```\n{reason}\n```", inline=False)
            embed.set_footer(text=f"Target ID: {user.id}", icon_url=self.bot.user.display_avatar.url)
            embed.timestamp = discord.utils.utcnow()

            return await interaction.response.send_message(embed=embed)

        # ----------------------------------------------------
        # MODE 2: INTERACTIVE MENU (NO ROLES SPECIFIED)
        # ----------------------------------------------------
        roles_to_remove: List[discord.Role] = []

        if not role and not second_role and not third_role:
            if not valid_removable_roles:
                embed = discord.Embed(
                    title=f"{EMOJI_CROSS} No Roles Available",
                    description=f"{user.mention} has no removable roles or you lack hierarchy permissions.",
                    color=discord.Color.red()
                )
                return await interaction.response.send_message(embed=embed, ephemeral=True)

            view = RoleSelectView(user, valid_removable_roles, moderator)
            embed = discord.Embed(
                title="⚙️ Select Roles to Remove",
                description=f"Choose up to 5 roles to remove from {user.mention} using the dropdown menu below.",
                color=discord.Color.blue()
            )
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            
            # Wait for user interaction with dropdown
            await view.wait()

            if not view.selected_role_ids:
                embed_timeout = discord.Embed(
                    title=f"{EMOJI_CROSS} Selection Timed Out",
                    description="No roles were selected. Command cancelled.",
                    color=discord.Color.red()
                )
                return await interaction.edit_original_response(embed=embed_timeout, view=None)

            roles_to_remove = [guild.get_role(rid) for rid in view.selected_role_ids if guild.get_role(rid)]

        # ----------------------------------------------------
        # MODE 3: DIRECT SPECIFICATION VIA COMMAND PARAMETERS
        # ----------------------------------------------------
        else:
            provided_roles = [r for r in [role, second_role, third_role] if r is not None]
            
            for r in provided_roles:
                # 1. Check if target actually has the role
                if r not in user.roles:
                    embed = discord.Embed(
                        title=f"{EMOJI_CROSS} Role Not Assigned",
                        description=f"{user.mention} does not have the {r.mention} role.",
                        color=discord.Color.red()
                    )
                    return await interaction.response.send_message(embed=embed, ephemeral=True)

                # 2. Managed Role Check
                if r.is_integration() or r.is_bot_managed():
                    embed = discord.Embed(
                        title=f"{EMOJI_CROSS} Managed Role Error",
                        description=f"The role {r.mention} is managed by an integration/bot and cannot be manually removed.",
                        color=discord.Color.red()
                    )
                    return await interaction.response.send_message(embed=embed, ephemeral=True)

                # 3. Moderator Hierarchy Check
                if r >= moderator.top_role and moderator.id != guild.owner_id:
                    embed = discord.Embed(
                        title=f"{EMOJI_CROSS} Hierarchy Error",
                        description=f"You cannot remove {r.mention} because it is equal to or higher than your highest role ({moderator.top_role.mention}).",
                        color=discord.Color.red()
                    )
                    return await interaction.response.send_message(embed=embed, ephemeral=True)

                # 4. Bot Hierarchy Check
                if r >= bot_member.top_role:
                    embed = discord.Embed(
                        title=f"{EMOJI_CROSS} Hierarchy Error",
                        description=f"I cannot remove {r.mention} because it is equal to or higher than my top role ({bot_member.top_role.mention}).",
                        color=discord.Color.red()
                    )
                    return await interaction.response.send_message(embed=embed, ephemeral=True)

                if r not in roles_to_remove:
                    roles_to_remove.append(r)

        if not roles_to_remove:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Invalid Selection",
                description="No valid roles were provided or selected for removal.",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # ----------------------------------------------------
        # CANCEL ACTIVE TEMP ROLES (IF REGISTERED IN ADDROLE COG)
        # ----------------------------------------------------
        addrole_cog = self.bot.get_cog("AddRoleCog")
        if addrole_cog and hasattr(addrole_cog, "temp_roles"):
            for r in roles_to_remove:
                addrole_cog.temp_roles = [
                    entry for entry in addrole_cog.temp_roles
                    if not (entry["guild_id"] == guild.id and entry["user_id"] == user.id and entry["role_id"] == r.id)
                ]

        # ----------------------------------------------------
        # EXECUTE ROLE REMOVAL
        # ----------------------------------------------------
        audit_reason = f"Role(s) removed by {moderator} ({moderator.id}) | Reason: {reason}"
        try:
            await user.remove_roles(*roles_to_remove, reason=audit_reason)
        except Exception as e:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Role Removal Failed",
                description=f"An error occurred while removing roles from {user.mention}: `{str(e)}`",
                color=discord.Color.red()
            )
            if interaction.response.is_done():
                return await interaction.followup.send(embed=embed, ephemeral=True)
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # ----------------------------------------------------
        # DIRECT MESSAGE NOTIFICATION
        # ----------------------------------------------------
        dm_sent = False
        roles_text = ", ".join([r.mention for r in roles_to_remove])
        dm_embed = discord.Embed(
            title=f"{EMOJI_CROSS} Role(s) Removed",
            description=f"The following role(s) were removed from your profile in **{guild.name}**:",
            color=discord.Color.dark_red()
        )
        dm_embed.add_field(name="Removed Role(s)", value=roles_text, inline=False)
        dm_embed.add_field(name="Moderator", value=f"{moderator}", inline=True)
        dm_embed.add_field(name="Reason", value=f"```\n{reason}\n```", inline=False)
        dm_embed.set_thumbnail(url=guild.icon.url if guild.icon else user.display_avatar.url)
        dm_embed.timestamp = discord.utils.utcnow()

        try:
            await user.send(embed=dm_embed)
            dm_sent = True
        except (discord.Forbidden, discord.HTTPException):
            dm_sent = False

        # ----------------------------------------------------
        # SERVER CHANNEL CONFIRMATION EMBED
        # ----------------------------------------------------
        primary_color = roles_to_remove[0].color if roles_to_remove[0].color.value != 0 else discord.Color.green()
        server_embed = discord.Embed(
            title=f"{EMOJI_TICK} Role(s) Removed Successfully",
            description=f"Successfully updated roles for {user.mention}.",
            color=primary_color
        )
        server_embed.set_thumbnail(url=user.display_avatar.url)
        server_embed.add_field(name="Target Member", value=f"{user.name} (`{user.id}`)", inline=True)
        server_embed.add_field(name="Removed Role(s)", value=roles_text, inline=True)
        server_embed.add_field(name="DM Status", value=f"`{'Sent' if dm_sent else 'Failed (DMs Closed)'}`", inline=True)
        server_embed.add_field(name="Moderator", value=f"{moderator.mention}", inline=False)
        server_embed.add_field(name="Reason", value=f"```\n{reason}\n```", inline=False)
        server_embed.set_footer(text=f"Target ID: {user.id}", icon_url=self.bot.user.display_avatar.url)
        server_embed.timestamp = discord.utils.utcnow()

        if interaction.response.is_done():
            await interaction.followup.send(embed=server_embed)
        else:
            await interaction.response.send_message(embed=server_embed)

    # ==========================================
    # ERROR HANDLING: Permissions & Arguments
    # ==========================================
    @removerole_command.error
    async def removerole_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            missing_perms = ", ".join([f"`{perm}`" for perm in error.missing_permissions])
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Permission Denied",
                description=f"{interaction.user.mention}, you lack permission(s): {missing_perms}",
                color=discord.Color.red()
            )
            embed.set_footer(text="Required Permission: MANAGE_ROLES")
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        elif isinstance(error, app_commands.BotMissingPermissions):
            missing_perms = ", ".join([f"`{perm}`" for perm in error.missing_permissions])
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Bot Permission Required",
                description=f"I am missing required permission(s): {missing_perms}",
                color=discord.Color.red()
            )
            embed.set_footer(text="Please grant the bot Manage Roles permission.")
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        elif isinstance(error, app_commands.MissingRequiredArgument):
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Missing Parameter",
                description=f"{interaction.user.mention}, missing argument: `{error.param.name}`.",
                color=discord.Color.red()
            )
            embed.set_footer(text="Usage: /removerole user:<member> [role:<role>] [reason:<text>]")
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        else:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Unexpected Error",
                description=f"An error occurred: `{str(error)}`",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(RemoveRoleCog(bot))
      
