import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, List

# Custom Emoji Constants
EMOJI_TICK = "<a:Tick:1536982741537656832>"
EMOJI_CROSS = "<:Cross:1536982744008106055>"


class NicknameActionView(discord.ui.View):
    """Interactive control view attached to nickname updates for instant rollback."""
    def __init__(self, cog: "NicknameCog", target: discord.Member, old_nick: Optional[str], moderator: discord.Member):
        super().__init__(timeout=120)
        self.cog = cog
        self.target = target
        self.old_nick = old_nick
        self.moderator = moderator

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.moderator.id:
            await interaction.response.send_message(
                f"{EMOJI_CROSS} Only {self.moderator.mention} can interact with these controls.",
                ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Revert Nickname", style=discord.ButtonStyle.danger, emoji="🔁")
    async def revert_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Reverts the target's nickname back to its previous state."""
        try:
            await self.target.edit(nick=self.old_nick, reason=f"Reverted via UI button by {interaction.user}")
            embed = discord.Embed(
                title=f"{EMOJI_TICK} Nickname Reverted",
                description=f"Reverted {self.target.mention}'s nickname back to `{self.old_nick or self.target.name}`.",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            self.stop()
        except Exception as e:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Revert Failed",
                description=f"Could not revert nickname: `{str(e)}`",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)


class NicknameCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def sanitize_nickname(self, text: str) -> str:
        """Sanitizes control characters and clamps string length to 32 chars."""
        cleaned = text.strip().replace("\n", "").replace("\r", "")
        return cleaned[:32]

    def format_template(self, template: str, member: discord.Member, role: Optional[discord.Role] = None) -> str:
        """Formats nickname string using dynamic user and server placeholders."""
        formatted = (
            template.replace("{user}", member.name)
            .replace("{display}", member.display_name)
            .replace("{server}", member.guild.name)
        )
        if role:
            formatted = formatted.replace("{role}", role.name)
        return self.sanitize_nickname(formatted)

    def can_modify_member(self, moderator: discord.Member, target: discord.Member, guild: discord.Guild) -> tuple[bool, str]:
        """Validates role hierarchy and owner status before editing nicknames."""
        if target.id == guild.owner_id:
            return False, "Cannot modify the Server Owner."

        if target.top_role >= moderator.top_role and moderator.id != guild.owner_id:
            return False, f"Target's top role ({target.top_role.mention}) is equal to or higher than yours."

        if target.top_role >= guild.me.top_role:
            return False, f"Target's top role ({target.top_role.mention}) is higher than or equal to my highest role."

        return True, ""

    # ==========================================
    # SLASH COMMAND: /setnick
    # ==========================================
    @app_commands.command(
        name="setnick",
        description="Change a member's nickname with optional template support."
    )
    @app_commands.checks.has_permissions(manage_nicknames=True)
    @app_commands.bot_has_permissions(manage_nicknames=True)
    @app_commands.describe(
        user="Target member to modify",
        nickname="New nickname (Supports {user}, {display}, {server})",
        reason="Reason for nickname change"
    )
    async def setnick_command(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        nickname: str,
        reason: str = "No reason provided"
    ):
        guild = interaction.guild
        can_mod, err_msg = self.can_modify_member(interaction.user, user, guild)

        if not can_mod:
            embed = discord.Embed(title=f"{EMOJI_CROSS} Hierarchy Restriction", description=err_msg, color=discord.Color.red())
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        old_nick = user.nick
        formatted_nick = self.format_template(nickname, user)

        try:
            await user.edit(nick=formatted_nick, reason=f"Changed by {interaction.user} | Reason: {reason}")
        except Exception as e:
            embed = discord.Embed(title=f"{EMOJI_CROSS} Update Failed", description=f"Error: `{str(e)}`", color=discord.Color.red())
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        embed = discord.Embed(
            title=f"{EMOJI_TICK} Nickname Updated Successfully",
            description=f"Updated nickname for {user.mention}.",
            color=discord.Color.green()
        )
        embed.add_field(name="Target Member", value=f"{user.name} (`{user.id}`)", inline=True)
        embed.add_field(name="Old Name", value=f"`{old_nick or user.name}`", inline=True)
        embed.add_field(name="New Nickname", value=f"`{formatted_nick}`", inline=True)
        embed.add_field(name="Reason", value=f"```\n{reason}\n```", inline=False)
        embed.set_footer(text=f"Moderator: {interaction.user}", icon_url=interaction.user.display_avatar.url)
        embed.timestamp = discord.utils.utcnow()

        view = NicknameActionView(self, user, old_nick, interaction.user)
        await interaction.response.send_message(embed=embed, view=view)

    # ==========================================
    # SLASH COMMAND: /resetnick
    # ==========================================
    @app_commands.command(
        name="resetnick",
        description="Reset a member's custom nickname back to default username."
    )
    @app_commands.checks.has_permissions(manage_nicknames=True)
    @app_commands.bot_has_permissions(manage_nicknames=True)
    @app_commands.describe(user="Target member to reset", reason="Reason for resetting nickname")
    async def resetnick_command(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        reason: str = "No reason provided"
    ):
        can_mod, err_msg = self.can_modify_member(interaction.user, user, interaction.guild)
        if not can_mod:
            embed = discord.Embed(title=f"{EMOJI_CROSS} Hierarchy Restriction", description=err_msg, color=discord.Color.red())
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        old_nick = user.display_name
        try:
            await user.edit(nick=None, reason=f"Reset by {interaction.user} | Reason: {reason}")
        except Exception as e:
            embed = discord.Embed(title=f"{EMOJI_CROSS} Reset Failed", description=f"Error: `{str(e)}`", color=discord.Color.red())
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        embed = discord.Embed(
            title=f"{EMOJI_TICK} Nickname Reset Successfully",
            description=f"Cleared custom nickname for {user.mention}.",
            color=discord.Color.green()
        )
        embed.add_field(name="Target Member", value=f"{user.name} (`{user.id}`)", inline=True)
        embed.add_field(name="Previous Name", value=f"`{old_nick}`", inline=True)
        embed.add_field(name="Restored Username", value=f"`{user.name}`", inline=True)
        embed.set_footer(text=f"Moderator: {interaction.user}", icon_url=interaction.user.display_avatar.url)
        embed.timestamp = discord.utils.utcnow()

        await interaction.response.send_message(embed=embed)

    # ==========================================
    # SLASH COMMAND: /add-tag
    # ==========================================
    @app_commands.command(
        name="add-tag",
        description="Append a prefix or suffix tag to a member or entire role (e.g. [VIP] Name)."
    )
    @app_commands.checks.has_permissions(manage_nicknames=True)
    @app_commands.bot_has_permissions(manage_nicknames=True)
    @app_commands.describe(
        user="Target member (Optional)",
        role="Target role group (Optional)",
        tag="Tag text to apply (e.g. [MOD])",
        position="Prefix (front) or Suffix (end)"
    )
    @app_commands.choices(position=[
        app_commands.Choice(name="Prefix (Front)", value="prefix"),
        app_commands.Choice(name="Suffix (End)", value="suffix")
    ])
    async def add_tag_command(
        self,
        interaction: discord.Interaction,
        tag: str,
        position: app_commands.Choice[str],
        user: Optional[discord.Member] = None,
        role: Optional[discord.Role] = None
    ):
        if not user and not role:
            embed = discord.Embed(title=f"{EMOJI_CROSS} Target Required", description="Select either a `user:` or a `role:` target.", color=discord.Color.red())
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        await interaction.response.defer()
        targets: List[discord.Member] = [user] if user else role.members
        success_count, failed_count = 0, 0

        for member in targets:
            can_mod, _ = self.can_modify_member(interaction.user, member, interaction.guild)
            if not can_mod:
                failed_count += 1
                continue

            current_name = member.display_name
            new_name = f"{tag} {current_name}" if position.value == "prefix" else f"{current_name} {tag}"
            sanitized = self.sanitize_nickname(new_name)

            try:
                await member.edit(nick=sanitized, reason=f"Tag applied by {interaction.user}")
                success_count += 1
            except Exception:
                failed_count += 1

        embed = discord.Embed(
            title=f"{EMOJI_TICK} Tag Operation Completed",
            description=f"Applied `{tag}` as a {position.name}.",
            color=discord.Color.green()
        )
        embed.add_field(name="Successful Updates", value=f"`{success_count}`", inline=True)
        embed.add_field(name="Skipped / Failed", value=f"`{failed_count}`", inline=True)
        embed.set_footer(text=f"Moderator: {interaction.user}", icon_url=interaction.user.display_avatar.url)
        embed.timestamp = discord.utils.utcnow()

        await interaction.followup.send(embed=embed)

    # ==========================================
    # SLASH COMMAND: /massnick
    # ==========================================
    @app_commands.command(
        name="massnick",
        description="Mass update nicknames for all members possessing a specific role with templates."
    )
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.bot_has_permissions(manage_nicknames=True)
    @app_commands.describe(
        role="Target role whose members will be updated",
        template="Template format (Supports {user}, {display}, {role})"
    )
    async def massnick_command(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        template: str
    ):
        await interaction.response.defer()
        success_count, failed_count = 0, 0

        for member in role.members:
            can_mod, _ = self.can_modify_member(interaction.user, member, interaction.guild)
            if not can_mod:
                failed_count += 1
                continue

            formatted_nick = self.format_template(template, member, role)
            try:
                await member.edit(nick=formatted_nick, reason=f"Mass nickname update by {interaction.user}")
                success_count += 1
            except Exception:
                failed_count += 1

        embed = discord.Embed(
            title=f"{EMOJI_TICK} Mass Nickname Update Complete",
            description=f"Updated members with role {role.mention}.",
            color=discord.Color.green()
        )
        embed.add_field(name="Successful Updates", value=f"`{success_count}`", inline=True)
        embed.add_field(name="Failed / Skipped", value=f"`{failed_count}`", inline=True)
        embed.add_field(name="Applied Template", value=f"```\n{template}\n```", inline=False)
        embed.set_footer(text=f"Executed by {interaction.user}", icon_url=interaction.user.display_avatar.url)
        embed.timestamp = discord.utils.utcnow()

        await interaction.followup.send(embed=embed)

    # ==========================================
    # SLASH COMMAND: /resetnick-all
    # ==========================================
    @app_commands.command(
        name="resetnick-all",
        description="EMERGENCY: Reset custom nicknames for ALL members across the server."
    )
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.bot_has_permissions(manage_nicknames=True)
    async def resetnick_all_command(self, interaction: discord.Interaction):
        await interaction.response.defer()
        success_count, failed_count = 0, 0

        for member in interaction.guild.members:
            if not member.nick:
                continue

            can_mod, _ = self.can_modify_member(interaction.user, member, interaction.guild)
            if not can_mod:
                failed_count += 1
                continue

            try:
                await member.edit(nick=None, reason=f"Server-wide nickname reset by {interaction.user}")
                success_count += 1
            except Exception:
                failed_count += 1

        embed = discord.Embed(
            title=f"{EMOJI_TICK} SERVER NICKNAME RESET COMPLETE",
            description=f"Cleared custom nicknames for **{success_count}** members in **{interaction.guild.name}**.",
            color=discord.Color.green()
        )
        embed.add_field(name="Cleared Nicknames", value=f"`{success_count}`", inline=True)
        embed.add_field(name="Skipped / Failed", value=f"`{failed_count}`", inline=True)
        embed.set_footer(text=f"Executed by {interaction.user}", icon_url=interaction.user.display_avatar.url)
        embed.timestamp = discord.utils.utcnow()

        await interaction.followup.send(embed=embed)

    # ==========================================
    # ERROR HANDLING
    # ==========================================
    @setnick_command.error
    @resetnick_command.error
    @add_tag_command.error
    @massnick_command.error
    @resetnick_all_command.error
    async def nickname_error_handler(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            missing_perms = ", ".join([f"`{p}`" for p in error.missing_permissions])
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
            missing_perms = ", ".join([f"`{p}`" for p in error.missing_permissions])
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
    await bot.add_cog(NicknameCog(bot))
      
