import time
import discord
from discord import app_commands
from discord.ext import commands
from typing import List, Dict

# Custom Emoji Constants
EMOJI_TICK = "<a:Tick:1536982741537656832>"
EMOJI_CROSS = "<:Cross:1536982744008106055>"

class BotStatsView(discord.ui.View):
    """Interactive UI buttons for refreshing metrics and inspecting command structures."""
    def __init__(self, cog: "BotStatsCog", author: discord.Member):
        super().__init__(timeout=120)
        self.cog = cog
        self.author = author

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                f"{EMOJI_CROSS} Only {self.author.mention} can interact with these controls.",
                ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Refresh Stats", style=discord.ButtonStyle.primary, emoji="🔁")
    async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Refreshes the live stats embed in real-time."""
        embed = self.cog.build_stats_embed(interaction)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Command List", style=discord.ButtonStyle.secondary, emoji="📜")
    async def commands_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Displays a categorized breakdown of all registered slash commands."""
        tree_commands = self.cog.bot.tree.get_commands()
        
        embed = discord.Embed(
            title=f"{EMOJI_TICK} Registered Slash Commands ({len(tree_commands)})",
            description="All active slash commands grouped by module:",
            color=discord.Color.blue()
        )

        cog_commands: Dict[str, List[str]] = {}
        for cmd in tree_commands:
            cog_name = cmd.binding.__class__.__name__ if cmd.binding else "Global / Unbound"
            cog_commands.setdefault(cog_name, []).append(f"`/{cmd.name}`")

        for cog_name, cmd_list in cog_commands.items():
            embed.add_field(
                name=f"📦 {cog_name}",
                value=", ".join(cmd_list),
                inline=False
            )

        embed.set_footer(text="Phantom Bot Command Registry", icon_url=self.cog.bot.user.display_avatar.url)
        embed.timestamp = discord.utils.utcnow()
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Loaded Cogs", style=discord.ButtonStyle.secondary, emoji="📂")
    async def cogs_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Lists all currently active cog extensions."""
        active_cogs = list(self.cog.bot.cogs.keys())
        cogs_formatted = "\n".join([f"• **{name}**" for name in active_cogs]) or "None"

        embed = discord.Embed(
            title=f"{EMOJI_TICK} Active Cog Modules ({len(active_cogs)})",
            description=cogs_formatted,
            color=discord.Color.green()
        )
        embed.set_footer(text="Phantom Bot System Architecture", icon_url=self.cog.bot.user.display_avatar.url)
        embed.timestamp = discord.utils.utcnow()
        await interaction.response.send_message(embed=embed, ephemeral=True)


class BotStatsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.start_time = time.time()

    def get_uptime(self) -> str:
        """Calculates and formats human-readable uptime."""
        delta = int(time.time() - self.start_time)
        days, remainder = divmod(delta, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)

        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        if seconds > 0 or not parts:
            parts.append(f"{seconds}s")

        return " ".join(parts)

    def build_stats_embed(self, interaction: discord.Interaction) -> discord.Embed:
        """Helper function to compile and format embed metrics."""
        # Guild & User Metrics
        total_servers = len(self.bot.guilds)
        total_members = sum(guild.member_count or 0 for guild in self.bot.guilds)
        avg_members = round(total_members / total_servers, 1) if total_servers > 0 else 0
        total_roles = sum(len(guild.roles) for guild in self.bot.guilds)

        # Channel Breakdown
        total_text = sum(len(guild.text_channels) for guild in self.bot.guilds)
        total_voice = sum(len(guild.voice_channels) for guild in self.bot.guilds)
        total_categories = sum(len(guild.categories) for guild in self.bot.guilds)
        total_channels = total_text + total_voice + total_categories

        # Application & Slash Command Metrics
        slash_commands_count = len(self.bot.tree.get_commands())
        latency_ms = round(self.bot.latency * 1000, 2)

        embed = discord.Embed(
            title=f"{EMOJI_TICK} {self.bot.user.name} — Live Metrics",
            description="Real-time overview of connected guilds, channels, roles, and slash commands.",
            color=discord.Color.blue()
        )

        if self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)

        # Guild & Reach Field
        embed.add_field(
            name="📊 Guild & User Reach",
            value=(
                f"• **Servers Joined:** `{total_servers:,}`\n"
                f"• **Total Users:** `{total_members:,}`\n"
                f"• **Avg Users/Server:** `{avg_members}`\n"
                f"• **Total Roles:** `{total_roles:,}`"
            ),
            inline=True
        )

        # Channels Breakdown Field
        embed.add_field(
            name="📁 Channel Count",
            value=(
                f"• **Total Channels:** `{total_channels:,}`\n"
                f"• **Text Channels:** `{total_text:,}`\n"
                f"• **Voice Channels:** `{total_voice:,}`\n"
                f"• **Categories:** `{total_categories:,}`"
            ),
            inline=True
        )

        # Application & Commands Field
        embed.add_field(
            name="⚡ Application & Commands",
            value=(
                f"• **Slash Commands:** `{slash_commands_count}`\n"
                f"• **Active Cogs Loaded:** `{len(self.bot.cogs)}`\n"
                f"• **Gateway Latency:** `{latency_ms} ms`\n"
                f"• **System Uptime:** `{self.get_uptime()}`"
            ),
            inline=False
        )

        embed.set_footer(
            text=f"Requested by {interaction.user} • Phantom Bot Systems",
            icon_url=interaction.user.display_avatar.url
        )
        embed.timestamp = discord.utils.utcnow()
        return embed

    # ==========================================
    # SLASH COMMAND: /botstats
    # ==========================================
    @app_commands.command(
        name="botstats",
        description="Display interactive server counts, channel metrics, and application command statistics."
    )
    async def botstats_command(self, interaction: discord.Interaction):
        embed = self.build_stats_embed(interaction)
        view = BotStatsView(self, interaction.user)
        await interaction.response.send_message(embed=embed, view=view)

    # ==========================================
    # ERROR HANDLING
    # ==========================================
    @botstats_command.error
    async def botstats_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        embed = discord.Embed(
            title=f"{EMOJI_CROSS} Error Fetching Statistics",
            description=f"An error occurred while compiling metrics: `{str(error)}`",
            color=discord.Color.red()
        )
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(BotStatsCog(bot))
      
