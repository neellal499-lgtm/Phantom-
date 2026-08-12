import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, List, Dict

# Custom Emoji Constants
EMOJI_TICK = "<a:Tick:1536982741537656832>"
EMOJI_CROSS = "<:Cross:1536982744008106055>"


class HelpCategorySelect(discord.ui.Select):
    """Dropdown menu for switching between cog/command categories."""
    def __init__(self, cog: "HelpCog", cogs_data: Dict[str, List[app_commands.Command]]):
        self.cog = cog
        self.cogs_data = cogs_data

        options = [
            discord.SelectOption(
                label="Home Overview",
                description="Return to the main help dashboard",
                emoji="🏠",
                value="home"
            )
        ]

        # Populate categories dynamically based on loaded cogs
        for cog_name in sorted(cogs_data.keys()):
            clean_name = cog_name.replace("Cog", "").title()
            cmd_count = len(cogs_data[cog_name])
            options.append(
                discord.SelectOption(
                    label=f"{clean_name} Module",
                    description=f"{cmd_count} command(s) available",
                    emoji="📁",
                    value=cog_name
                )
            )

        super().__init__(
            placeholder="Select a category to view commands...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="help_category_select"
        )

    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]

        if selected == "home":
            embed = await self.cog.build_home_embed(interaction)
        else:
            embed = self.cog.build_cog_embed(selected, self.cogs_data.get(selected, []))

        await interaction.response.edit_message(embed=embed)


class HelpControlView(discord.ui.View):
    """View container for help dropdown and action buttons."""
    def __init__(self, cog: "HelpCog", cogs_data: Dict[str, List[app_commands.Command]], author: discord.Member):
        super().__init__(timeout=180)
        self.cog = cog
        self.author = author
        self.add_item(HelpCategorySelect(cog, cogs_data))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                f"{EMOJI_CROSS} Only {self.author.mention} can interact with this help menu.",
                ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Reset", style=discord.ButtonStyle.secondary, emoji="🏠", row=1)
    async def home_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = await self.cog.build_home_embed(interaction)
        await interaction.response.edit_message(embed=embed)

    @discord.ui.button(label="Dismiss", style=discord.ButtonStyle.danger, emoji="🗑️", row=1)
    async def dismiss_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.delete()


class HelpCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def get_cogs_command_map(self) -> Dict[str, List[app_commands.Command]]:
        """Maps loaded Cogs to their respective Slash Commands dynamically."""
        cogs_map: Dict[str, List[app_commands.Command]] = {}

        # Scan all commands registered in bot tree
        for cmd in self.bot.tree.get_commands():
            cog_name = "Uncategorized"
            if hasattr(cmd, "binding") and cmd.binding:
                cog_name = cmd.binding.__class__.__name__

            if cog_name not in cogs_map:
                cogs_map[cog_name] = []
            cogs_map[cog_name].append(cmd)

        return cogs_map

    async def build_home_embed(self, interaction: discord.Interaction) -> discord.Embed:
        """Constructs the primary home page help embed."""
        latency = round(self.bot.latency * 1000)
        total_cogs = len(self.bot.cogs)
        total_cmds = len(self.bot.tree.get_commands())

        embed = discord.Embed(
            title="📚 Phantom Bot — Command Help Center",
            description=(
                f"Welcome to the **Phantom Bot** command directory!\n"
                f"Use the **dropdown menu below** to explore commands categorized by module, or view details for a specific command using `/help command:[name]`.\n"
            ),
            color=discord.Color.blue()
        )

        embed.add_field(
            name="📊 System Stats",
            value=(
                f"• **Latency:** `{latency}ms`\n"
                f"• **Active Modules:** `{total_cogs}`\n"
                f"• **Total Slash Commands:** `{total_cmds}`"
            ),
            inline=True
        )

        embed.add_field(
            name="💡 Tips",
            value=(
                "• All commands use Discord's `/` Slash interface.\n"
                "• Requires proper role permissions for moderation commands."
            ),
            inline=True
        )

        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.set_footer(
            text=f"Requested by {interaction.user} • Select a category below",
            icon_url=interaction.user.display_avatar.url
        )
        embed.timestamp = discord.utils.utcnow()
        return embed

    def build_cog_embed(self, cog_name: str, commands_list: List[app_commands.Command]) -> discord.Embed:
        """Constructs a category-specific help embed listing commands."""
        clean_name = cog_name.replace("Cog", "").title()
        embed = discord.Embed(
            title=f"📁 {clean_name} Module Commands",
            description=f"Showing all **{len(commands_list)}** available slash commands in this category:",
            color=discord.Color.purple()
        )

        if not commands_list:
            embed.description = "No slash commands registered in this module."
        else:
            for cmd in commands_list:
                # Format parameters if available
                params = []
                if hasattr(cmd, "parameters") and cmd.parameters:
                    for p in cmd.parameters:
                        req = "" if p.required else " [Optional]"
                        params.append(f"`{p.name}`{req}")
                param_str = f"\n└ **Inputs:** {', '.join(params)}" if params else ""

                desc = cmd.description or "No description provided."
                embed.add_field(
                    name=f"/{cmd.name}",
                    value=f"{desc}{param_str}",
                    inline=False
                )

        embed.set_footer(text=f"Phantom Bot • Category: {clean_name}")
        embed.timestamp = discord.utils.utcnow()
        return embed

    # ==========================================
    # AUTOCOMPLETE FOR /help command:[name]
    # ==========================================
    async def command_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> List[app_commands.Choice[str]]:
        """Provides autocomplete choices for specific slash commands."""
        choices = []
        for cmd in self.bot.tree.get_commands():
            if current.lower() in cmd.name.lower():
                choices.append(app_commands.Choice(name=f"/{cmd.name}", value=cmd.name))
            if len(choices) >= 25:
                break
        return choices

    # ==========================================
    # SLASH COMMAND: /help
    # ==========================================
    @app_commands.command(
        name="help",
        description="Display interactive command documentation and system overview."
    )
    @app_commands.describe(command="Optional specific command name to inspect")
    @app_commands.autocomplete(command=command_autocomplete)
    async def help_command(
        self,
        interaction: discord.Interaction,
        command: Optional[str] = None
    ):
        cogs_data = self.get_cogs_command_map()

        # CASE 1: User requested help for a specific command
        if command:
            target_cmd = self.bot.tree.get_command(command.lower())
            if not target_cmd:
                embed = discord.Embed(
                    title=f"{EMOJI_CROSS} Command Not Found",
                    description=f"Could not find any registered command matching `/{command}`.",
                    color=discord.Color.red()
                )
                return await interaction.response.send_message(embed=embed, ephemeral=True)

            embed = discord.Embed(
                title=f"📖 Command Info: /{target_cmd.name}",
                description=f"**Description:**\n{target_cmd.description or 'No description provided.'}",
                color=discord.Color.blue()
            )

            if hasattr(target_cmd, "parameters") and target_cmd.parameters:
                params_desc = []
                for p in target_cmd.parameters:
                    opt = "*(Optional)*" if not p.required else "**(Required)**"
                    p_desc = p.description or "No description."
                    params_desc.append(f"• `{p.name}` {opt}: {p_desc}")
                embed.add_field(name="Command Parameters", value="\n".join(params_desc), inline=False)

            embed.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
            embed.timestamp = discord.utils.utcnow()
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # CASE 2: Send Interactive Dropdown Help Dashboard
        embed = await self.build_home_embed(interaction)
        view = HelpControlView(self, cogs_data, interaction.user)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # ==========================================
    # ERROR HANDLING
    # ==========================================
    @help_command.error
    async def help_error_handler(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        embed = discord.Embed(
            title=f"{EMOJI_CROSS} Help System Error",
            description=f"An error occurred while loading help docs: `{str(error)}`",
            color=discord.Color.red()
        )
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))

