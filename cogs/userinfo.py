import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, List

# Custom Emoji Constants
EMOJI_TICK = "<a:Tick:1536982741537656832>"
EMOJI_CROSS = "<:Cross:1536982744008106055>"


class UserInfoView(discord.ui.View):
    """Interactive control view for detailed user inspection."""
    def __init__(self, target: discord.Member, full_user: discord.User, author: discord.Member):
        super().__init__(timeout=120)
        self.target = target
        self.full_user = full_user
        self.author = author

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                f"{EMOJI_CROSS} Only {self.author.mention} can interact with these controls.",
                ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Avatars & Banner", style=discord.ButtonStyle.primary, emoji="🖼️")
    async def avatar_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Displays high-res avatar and banner download links."""
        global_avatar = self.full_user.avatar.url if self.full_user.avatar else None
        server_avatar = self.target.guild_avatar.url if self.target.guild_avatar else None
        banner_url = self.full_user.banner.url if hasattr(self.full_user, "banner") and self.full_user.banner else None

        embed = discord.Embed(
            title=f"🖼️ Media Assets — {self.target.name}",
            color=self.target.color if self.target.color.value != 0 else discord.Color.blue()
        )

        links = []
        if global_avatar:
            links.append(f"[Global Avatar]({global_avatar})")
        if server_avatar:
            links.append(f"[Server Avatar]({server_avatar})")
        if banner_url:
            links.append(f"[Profile Banner]({banner_url})")

        embed.description = " • ".join(links) if links else "No custom avatars or banners set."

        display_image = server_avatar or global_avatar or banner_url
        if display_image:
            embed.set_image(url=display_image)

        embed.set_footer(text="Phantom Media Viewer", icon_url=interaction.user.display_avatar.url)
        embed.timestamp = discord.utils.utcnow()
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Full Permissions", style=discord.ButtonStyle.secondary, emoji="🔑")
    async def permissions_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Displays complete permission set breakdown."""
        perms = self.target.guild_permissions
        if perms.administrator:
            perm_text = "• `ADMINISTRATOR` (Has all permissions granted)"
        else:
            allowed_perms = [f"• `{perm.replace('_', ' ').title()}`" for perm, allowed in perms if allowed]
            perm_text = "\n".join(allowed_perms) if allowed_perms else "• No special server permissions."

        embed = discord.Embed(
            title=f"🔑 Full Permission List — {self.target.name}",
            description=perm_text[:4000],
            color=discord.Color.purple()
        )
        embed.set_footer(text="Phantom Permission Audit", icon_url=interaction.user.display_avatar.url)
        embed.timestamp = discord.utils.utcnow()
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Public Badges", style=discord.ButtonStyle.secondary, emoji="🚩")
    async def badges_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Lists user flags and public Discord badges."""
        flags = self.full_user.public_flags
        badge_list = []

        if flags.staff:
            badge_list.append("Discord Employee 🛠️")
        if flags.partner:
            badge_list.append("Partnered Server Owner ♾️")
        if flags.hypesquad:
            badge_list.append("HypeSquad Events 🎟️")
        if flags.bug_hunter:
            badge_list.append("Bug Hunter Level 1 🐛")
        if flags.bug_hunter_level_2:
            badge_list.append("Bug Hunter Level 2 🐛")
        if flags.hypesquad_bravery:
            badge_list.append("HypeSquad Bravery 🛡️")
        if flags.hypesquad_brilliance:
            badge_list.append("HypeSquad Brilliance 💎")
        if flags.hypesquad_balance:
            badge_list.append("HypeSquad Balance ⚖️")
        if flags.early_supporter:
            badge_list.append("Early Supporter 👑")
        if flags.active_developer:
            badge_list.append("Active Developer 💻")
        if flags.verified_bot_developer:
            badge_list.append("Early Verified Bot Developer 🤖")

        formatted_badges = "\n".join([f"• **{b}**" for b in badge_list]) if badge_list else "No public Discord badges detected."

        embed = discord.Embed(
            title=f"🚩 Public Badges & Flags — {self.target.name}",
            description=formatted_badges,
            color=discord.Color.gold()
        )
        embed.set_footer(text="Phantom Badge Inspector", icon_url=interaction.user.display_avatar.url)
        embed.timestamp = discord.utils.utcnow()
        await interaction.response.send_message(embed=embed, ephemeral=True)


class UserInfoCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def get_join_position(self, member: discord.Member) -> int:
        """Calculates exact numerical join order in the server."""
        sorted_members = sorted(member.guild.members, key=lambda m: m.joined_at or member.created_at)
        try:
            return sorted_members.index(member) + 1
        except ValueError:
            return 0

    def get_activities_text(self, member: discord.Member) -> str:
        """Formats active user status and activity status."""
        if not member.activities:
            return "`No active status/activity`"

        activity_lines = []
        for act in member.activities:
            if isinstance(act, discord.CustomActivity):
                activity_lines.append(f"• **Custom Status:** {act.name or ''}")
            elif isinstance(act, discord.Spotify):
                activity_lines.append(f"• **Spotify:** Listening to `{act.title}` by `{act.artist}`")
            elif act.type == discord.ActivityType.playing:
                activity_lines.append(f"• **Playing:** `{act.name}`")
            elif act.type == discord.ActivityType.streaming:
                activity_lines.append(f"• **Streaming:** [{act.name}]({act.url})")
            elif act.type == discord.ActivityType.watching:
                activity_lines.append(f"• **Watching:** `{act.name}`")

        return "\n".join(activity_lines) if activity_lines else "`No notable activity`"

    # ==========================================
    # SLASH COMMAND: /userinfo
    # ==========================================
    @app_commands.command(
        name="userinfo",
        description="Display interactive, advanced profile analytics, dates, roles, and permissions."
    )
    @app_commands.guild_only()
    @app_commands.describe(user="The member to inspect (Defaults to yourself)")
    async def userinfo_command(
        self, 
        interaction: discord.Interaction, 
        user: Optional[discord.Member] = None
    ):
        target: discord.Member = user or interaction.user
        guild = interaction.guild

        await interaction.response.defer()

        # Fetch complete User object to retrieve profile banner
        try:
            full_user = await self.bot.fetch_user(target.id)
        except Exception:
            full_user = target

        # Dates & Join Metrics
        joined_at = f"<t:{int(target.joined_at.timestamp())}:F> (<t:{int(target.joined_at.timestamp())}:R>)" if target.joined_at else "`Unknown`"
        created_at = f"<t:{int(target.created_at.timestamp())}:F> (<t:{int(target.created_at.timestamp())}:R>)"
        join_pos = self.get_join_position(target)

        # Roles Processing
        sorted_roles = [r.mention for r in sorted(target.roles, key=lambda r: r.position, reverse=True) if not r.is_default()]
        roles_display = ", ".join(sorted_roles[:8]) if sorted_roles else "`No Custom Roles`"
        if len(sorted_roles) > 8:
            roles_display += f" *(+{len(sorted_roles) - 8} more)*"

        # Status & Presence
        status_emoji = {
            discord.Status.online: "🟢 Online",
            discord.Status.idle: "🟡 Idle",
            discord.Status.dnd: "🔴 Do Not Disturb",
            discord.Status.offline: "⚪ Offline"
        }.get(target.status, "⚪ Offline")

        # Acknowledgements
        ack = "Server Member"
        if target.id == guild.owner_id:
            ack = "👑 Server Owner"
        elif target.guild_permissions.administrator:
            ack = "🛡️ Server Administrator"
        elif target.guild_permissions.manage_guild or target.guild_permissions.ban_members:
            ack = "⚔️ Server Moderator"
        elif target.bot:
            ack = "🤖 Bot Application"

        # Build Main Embed
        embed_color = target.color if target.color.value != 0 else discord.Color.blue()
        embed = discord.Embed(
            title=f"{EMOJI_TICK} Profile Analytics — {target.name}",
            color=embed_color
        )
        embed.set_thumbnail(url=target.display_avatar.url)

        # Identity Field
        embed.add_field(
            name="👤 Identity & Account",
            value=(
                f"• **Username:** `{target.name}`\n"
                f"• **Display Name:** `{target.display_name}`\n"
                f"• **User ID:** `{target.id}`\n"
                f"• **Hierarchy Ack:** `{ack}`"
            ),
            inline=True
        )

        # Status & Join Order
        embed.add_field(
            name="📡 Status & Server Position",
            value=(
                f"• **Presence:** {status_emoji}\n"
                f"• **Join Rank:** `#{join_pos}` of `{guild.member_count}`\n"
                f"• **Highest Role:** {target.top_role.mention if target.top_role else 'None'}\n"
                f"• **Booster:** `{'Yes' if target.premium_since else 'No'}`"
            ),
            inline=True
        )

        # Presence / Activity
        embed.add_field(
            name="🎮 Active Activity / Rich Presence",
            value=self.get_activities_text(target),
            inline=False
        )

        # Dates Field
        embed.add_field(
            name="📅 Timestamps",
            value=(
                f"• **Joined Server:** {joined_at}\n"
                f"• **Created Account:** {created_at}"
            ),
            inline=False
        )

        # Roles Field
        embed.add_field(
            name=f"🎭 Server Roles ({len(sorted_roles)})",
            value=roles_display,
            inline=False
        )

        # Set Profile Banner if present
        if hasattr(full_user, "banner") and full_user.banner:
            embed.set_image(url=full_user.banner.url)

        embed.set_footer(
            text=f"Requested by {interaction.user} • Phantom User Matrix",
            icon_url=interaction.user.display_avatar.url
        )
        embed.timestamp = discord.utils.utcnow()

        view = UserInfoView(target, full_user, interaction.user)
        await interaction.followup.send(embed=embed, view=view)

    # ==========================================
    # ERROR HANDLING
    # ==========================================
    @userinfo_command.error
    async def userinfo_error_handler(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        embed = discord.Embed(
            title=f"{EMOJI_CROSS} Error Fetching User Analytics",
            description=f"An error occurred while inspecting user: `{str(error)}`",
            color=discord.Color.red()
        )
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(UserInfoCog(bot))
          
