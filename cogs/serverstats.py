import discord
from discord import app_commands
from discord.ext import commands

# Custom Emoji Constants
EMOJI_TICK = "<a:Tick:1536982741537656832>"
EMOJI_CROSS = "<:Cross:1536982744008106055>"

class ServerStatsView(discord.ui.View):
    """Interactive buttons for exploring server metrics in detail."""
    def __init__(self, cog: "ServerStatsCog", guild: discord.Guild, author: discord.Member):
        super().__init__(timeout=120)
        self.cog = cog
        self.guild = guild
        self.author = author

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                f"{EMOJI_CROSS} Only {self.author.mention} can interact with these controls.",
                ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.primary, emoji="🔁")
    async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Refreshes live server statistics."""
        embed = self.cog.build_main_embed(self.guild, interaction.user)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Members", style=discord.ButtonStyle.secondary, emoji="👥")
    async def members_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Displays presence and status breakdown of members."""
        guild = self.guild
        total_members = guild.member_count or len(guild.members)
        bot_count = sum(1 for m in guild.members if m.bot)
        human_count = total_members - bot_count

        online = sum(1 for m in guild.members if m.status == discord.Status.online)
        idle = sum(1 for m in guild.members if m.status == discord.Status.idle)
        dnd = sum(1 for m in guild.members if m.status == discord.Status.dnd)
        offline = sum(1 for m in guild.members if m.status == discord.Status.offline)

        embed = discord.Embed(
            title=f"👥 Member & Presence Metrics — {guild.name}",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="Member Distribution",
            value=f"• **Total Members:** `{total_members:,}`\n• **Humans:** `{human_count:,}`\n• **Bots:** `{bot_count:,}`",
            inline=False
        )
        embed.add_field(
            name="Presence Breakdown",
            value=f"🟢 **Online:** `{online:,}`\n🟡 **Idle:** `{idle:,}`\n🔴 **DND:** `{dnd:,}`\n⚪ **Offline:** `{offline:,}`",
            inline=False
        )
        embed.set_footer(text="Phantom Bot Member Analytics", icon_url=self.cog.bot.user.display_avatar.url)
        embed.timestamp = discord.utils.utcnow()
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Top Roles", style=discord.ButtonStyle.secondary, emoji="🎭")
    async def roles_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Lists top roles by position and member counts."""
        sorted_roles = sorted(self.guild.roles, key=lambda r: r.position, reverse=True)
        # Exclude @everyone
        roles = [r for r in sorted_roles if not r.is_default()][:15]

        role_list = "\n".join([f"`#{r.position}` {r.mention} — `{len(r.members)} members`" for r in roles]) or "No custom roles."

        embed = discord.Embed(
            title=f"🎭 Highest Server Roles ({len(self.guild.roles)} Total)",
            description=role_list,
            color=discord.Color.gold()
        )
        embed.set_footer(text="Phantom Bot Hierarchy Overview", icon_url=self.cog.bot.user.display_avatar.url)
        embed.timestamp = discord.utils.utcnow()
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Boosts & Features", style=discord.ButtonStyle.secondary, emoji="🚀")
    async def boosts_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Shows server boosts, perks, and active features."""
        guild = self.guild
        boost_count = guild.premium_subscription_count or 0
        boost_tier = guild.premium_tier
        subscribers = len(guild.premium_subscribers)

        features = ", ".join([f"`{f.replace('_', ' ').title()}`" for f in guild.features[:10]]) or "None"

        embed = discord.Embed(
            title=f"🚀 Server Boost & Feature Perks — {guild.name}",
            color=discord.Color.purple()
        )
        embed.add_field(
            name="Boost Status",
            value=f"• **Level:** `Tier {boost_tier}`\n• **Boost Count:** `{boost_count}`\n• **Active Boosters:** `{subscribers}`",
            inline=False
        )
        embed.add_field(
            name="Key Server Features",
            value=features,
            inline=False
        )
        embed.set_footer(text="Phantom Bot Server Perks", icon_url=self.cog.bot.user.display_avatar.url)
        embed.timestamp = discord.utils.utcnow()
        await interaction.response.send_message(embed=embed, ephemeral=True)


class ServerStatsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def build_main_embed(self, guild: discord.Guild, user: discord.User) -> discord.Embed:
        """Helper to construct the main comprehensive server statistics embed."""
        # Member Breakdown
        total_members = guild.member_count or len(guild.members)
        bot_count = sum(1 for member in guild.members if member.bot)
        human_count = total_members - bot_count

        # Channel Breakdown
        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)
        stage_channels = len(guild.stage_channels)
        categories = len(guild.categories)
        total_channels = text_channels + voice_channels + stage_channels + categories

        # Roles, Emojis, Boosts
        role_count = len(guild.roles)
        emoji_count = len(guild.emojis)
        static_emojis = sum(1 for e in guild.emojis if not e.animated)
        animated_emojis = emoji_count - static_emojis
        sticker_count = len(guild.stickers)

        boost_count = guild.premium_subscription_count or 0
        boost_tier = guild.premium_tier

        # Server Information & Dates
        created_at = f"<t:{int(guild.created_at.timestamp())}:D> (<t:{int(guild.created_at.timestamp())}:R>)"
        owner = guild.owner.mention if guild.owner else f"`ID: {guild.owner_id}`"
        verification_lvl = str(guild.verification_level).capitalize()

        embed = discord.Embed(
            title=f"{EMOJI_TICK} {guild.name} — Server Overview",
            description=f"Advanced real-time metrics and structural configuration for **{guild.name}**.",
            color=discord.Color.purple()
        )

        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        # Member Statistics
        embed.add_field(
            name="👥 Member Reach",
            value=(
                f"• **Total Members:** `{total_members:,}`\n"
                f"• **Humans:** `{human_count:,}`\n"
                f"• **Bots:** `{bot_count:,}`"
            ),
            inline=True
        )

        # Channels Breakdown
        embed.add_field(
            name="📁 Channels",
            value=(
                f"• **Total Channels:** `{total_channels:,}`\n"
                f"• **Voice Channels:** `{voice_channels:,}`\n"
                f"• **Text Channels:** `{text_channels:,}`\n"
                f"• **Categories:** `{categories:,}`"
            ),
            inline=True
        )

        # Assets & Emojis
        embed.add_field(
            name="🎨 Assets & Customization",
            value=(
                f"• **Roles:** `{role_count}` Roles\n"
                f"• **Emojis:** `{emoji_count}` (`{static_emojis}` static / `{animated_emojis}` anim)\n"
                f"• **Stickers:** `{sticker_count}` Stickers"
            ),
            inline=False
        )

        # Boosts & Security
        embed.add_field(
            name="🚀 Boosts & Security",
            value=(
                f"• **Boost Status:** `{boost_count}` Boosts (`Level {boost_tier}`)\n"
                f"• **Verification:** `{verification_lvl}`\n"
                f"• **Explicit Filter:** `{str(guild.explicit_content_filter).replace('_', ' ').title()}`"
            ),
            inline=False
        )

        # Server Information
        embed.add_field(
            name="ℹ️ Core Information",
            value=(
                f"• **Server Owner:** {owner}\n"
                f"• **Server ID:** `{guild.id}`\n"
                f"• **Created On:** {created_at}"
            ),
            inline=False
        )

        if guild.banner:
            embed.set_image(url=guild.banner.url)

        embed.set_footer(
            text=f"Requested by {user} • Phantom Bot",
            icon_url=user.display_avatar.url
        )
        embed.timestamp = discord.utils.utcnow()

        return embed

    # ==========================================
    # SLASH COMMAND: /server-stats
    # ==========================================
    @app_commands.command(
        name="server-stats",
        description="Display interactive, detailed statistics and configuration for the current server."
    )
    @app_commands.guild_only()
    async def server_stats_command(self, interaction: discord.Interaction):
        embed = self.build_main_embed(interaction.guild, interaction.user)
        view = ServerStatsView(self, interaction.guild, interaction.user)
        await interaction.response.send_message(embed=embed, view=view)

    # ==========================================
    # ERROR HANDLING
    # ==========================================
    @server_stats_command.error
    async def server_stats_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        embed = discord.Embed(
            title=f"{EMOJI_CROSS} Error Fetching Server Stats",
            description=f"An error occurred while compiling server metrics: `{str(error)}`",
            color=discord.Color.red()
        )
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(ServerStatsCog(bot))
                         
