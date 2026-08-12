import sqlite3
import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, List, Dict

# Custom Emoji Constants
EMOJI_TICK = "<a:Tick:1536982741537656832>"
EMOJI_CROSS = "<:Cross:1536982744008106055>"
DB_FILE = "welcome_configs.db"


class WelcomeManageView(discord.ui.View):
    """Interactive control view for managing active welcome channel configurations."""
    def __init__(self, cog: "WelcomeCog", guild_id: int, author: discord.Member, configs: List[dict]):
        super().__init__(timeout=120)
        self.cog = cog
        self.guild_id = guild_id
        self.author = author
        self.configs = configs

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                f"{EMOJI_CROSS} Only {self.author.mention} can control this dashboard.",
                ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Test Setup #1", style=discord.ButtonStyle.primary, emoji="🧪", row=0)
    async def test_one(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.run_test_setup(interaction, 1)

    @discord.ui.button(label="Test Setup #2", style=discord.ButtonStyle.primary, emoji="🧪", row=0)
    async def test_two(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.run_test_setup(interaction, 2)

    @discord.ui.button(label="Test Setup #3", style=discord.ButtonStyle.primary, emoji="🧪", row=0)
    async def test_three(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.run_test_setup(interaction, 3)

    @discord.ui.button(label="Clear All Setups", style=discord.ButtonStyle.danger, emoji="🗑️", row=1)
    async def clear_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("DELETE FROM welcome_setups WHERE guild_id = ?", (self.guild_id,))
            await db.commit()

        embed = discord.Embed(
            title=f"{EMOJI_TICK} All Welcome Setups Deleted",
            description="Successfully cleared all welcome message configurations for this server.",
            color=discord.Color.green()
        )
        await interaction.response.edit_message(embed=embed, view=None)


class WelcomeCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        """Initializes SQLite database table on cog load."""
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS welcome_setups (
                    guild_id INTEGER,
                    config_id INTEGER,
                    channel_id INTEGER,
                    title TEXT,
                    line_1 TEXT,
                    line_2 TEXT,
                    line_3 TEXT,
                    line_4 TEXT,
                    line_5 TEXT,
                    line_6 TEXT,
                    banner TEXT,
                    embed_color TEXT,
                    ping_user INTEGER,
                    PRIMARY KEY (guild_id, config_id)
                )
            """)
            await db.commit()

    def format_text(self, text: str, member: discord.Member, channel: Optional[discord.TextChannel] = None) -> str:
        """Helper to replace placeholders dynamically."""
        if not text:
            return ""
        formatted = (
            text.replace("{user}", member.mention)
            .replace("{username}", member.name)
            .replace("{server}", member.guild.name)
            .replace("{membercount}", str(member.guild.member_count))
        )
        if channel:
            formatted = formatted.replace("{channel}", channel.mention)
        return formatted

    def parse_color(self, hex_code: Optional[str]) -> discord.Color:
        """Parses custom hex colors safely."""
        if not hex_code:
            return discord.Color.blue()
        hex_clean = hex_code.lstrip("#")
        try:
            return discord.Color(int(hex_clean, 16))
        except ValueError:
            return discord.Color.blue()

    def build_welcome_embed(self, config: dict, member: discord.Member, channel: Optional[discord.TextChannel] = None) -> discord.Embed:
        """Helper to construct the welcome embed from database config dict."""
        title_formatted = self.format_text(config["title"], member, channel)
        
        lines = [
            config["line_1"], config["line_2"], config["line_3"],
            config["line_4"], config["line_5"], config["line_6"]
        ]
        body_lines = [self.format_text(l, member, channel) for l in lines if l and l.strip()]
        description_text = "\n".join(body_lines)

        embed_color = self.parse_color(config.get("embed_color"))
        embed = discord.Embed(
            title=title_formatted,
            description=description_text,
            color=embed_color
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        
        if config.get("banner"):
            embed.set_image(url=config["banner"])

        embed.set_footer(
            text=f"Member #{member.guild.member_count} • {member.guild.name}",
            icon_url=member.guild.icon.url if member.guild.icon else None
        )
        embed.timestamp = discord.utils.utcnow()
        return embed

    async def get_guild_configs(self, guild_id: int) -> List[dict]:
        """Fetches all active welcome configurations for a guild from SQLite."""
        async with aiosqlite.connect(DB_FILE) as db:
            db.row_factory = sqlite3.Row
            async with db.execute("SELECT * FROM welcome_setups WHERE guild_id = ?", (guild_id,)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def run_test_setup(self, interaction: discord.Interaction, config_id: int):
        """Internal helper to execute test welcome embeds."""
        configs = await self.get_guild_configs(interaction.guild_id)
        target = next((c for c in configs if c["config_id"] == config_id), None)

        if not target:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Setup Not Found",
                description=f"No welcome configuration exists for ID `#{config_id}`.",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        channel = interaction.guild.get_channel(target["channel_id"])
        if not channel:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Channel Missing",
                description="The configured welcome channel no longer exists.",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        test_embed = self.build_welcome_embed(target, interaction.user, channel)
        ping_content = f"**[TEST PREVIEW]** Welcome {interaction.user.mention}!" if target.get("ping_user") else "**[TEST PREVIEW]**"
        
        try:
            await channel.send(content=ping_content, embed=test_embed)
            embed_resp = discord.Embed(
                title=f"{EMOJI_TICK} Test Sent",
                description=f"Sent preview for Setup `#{config_id}` to {channel.mention}.",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed_resp, ephemeral=True)
        except Exception as e:
            embed_resp = discord.Embed(
                title=f"{EMOJI_CROSS} Test Delivery Failed",
                description=f"Error sending to {channel.mention}: `{str(e)}`",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed_resp, ephemeral=True)

    # ==========================================
    # SLASH COMMAND: /create-welcome
    # ==========================================
    @app_commands.command(
        name="create-welcome",
        description="Configure an advanced welcome message setup (Max 3 per server)."
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(
        channel="Destination channel for welcome messages",
        title="Welcome Embed Title (Placeholders: {user}, {server}, {membercount})",
        line_1="Line 1 of welcome body",
        line_2="Line 2 of welcome body",
        line_3="Line 3 of welcome body",
        line_4="Line 4 of welcome body",
        line_5="Line 5 of welcome body",
        line_6="Line 6 of welcome body",
        banner="Optional: Image or GIF URL for embed banner",
        embed_color="Optional: Hex color code (e.g. #3498db)",
        ping_user="Optional: Mention the user outside the embed (True/False)"
    )
    async def create_welcome(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        title: str,
        line_1: str,
        line_2: str,
        line_3: str,
        line_4: str,
        line_5: str,
        line_6: str,
        banner: Optional[str] = None,
        embed_color: Optional[str] = "#3498db",
        ping_user: bool = True
    ):
        guild_id = interaction.guild_id
        existing_configs = await self.get_guild_configs(guild_id)

        if len(existing_configs) >= 3:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Configuration Limit Reached",
                description="This server already has **3 active welcome setups** (Maximum Limit). Delete one first using `/delete-welcome`.",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        existing_ids = {c["config_id"] for c in existing_configs}
        assigned_id = next(i for i in range(1, 4) if i not in existing_ids)

        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("""
                INSERT INTO welcome_setups 
                (guild_id, config_id, channel_id, title, line_1, line_2, line_3, line_4, line_5, line_6, banner, embed_color, ping_user)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                guild_id, assigned_id, channel.id, title,
                line_1, line_2, line_3, line_4, line_5, line_6,
                banner, embed_color, 1 if ping_user else 0
            ))
            await db.commit()

        embed = discord.Embed(
            title=f"{EMOJI_TICK} Welcome Setup Saved (ID: #{assigned_id})",
            description=f"Welcome messages will now post to {channel.mention}.",
            color=discord.Color.green()
        )
        embed.add_field(name="Channel", value=channel.mention, inline=True)
        embed.add_field(name="Setup ID", value=f"`#{assigned_id}`", inline=True)
        embed.add_field(name="Ping User", value=f"`{ping_user}`", inline=True)
        embed.add_field(name="Title Template", value=f"```\n{title}\n```", inline=False)
        embed.set_footer(text="Use /test-welcome to preview this configuration.")
        embed.timestamp = discord.utils.utcnow()

        await interaction.response.send_message(embed=embed)

    # ==========================================
    # SLASH COMMAND: /list-welcome
    # ==========================================
    @app_commands.command(
        name="list-welcome",
        description="List and manage all active welcome channel configurations."
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def list_welcome(self, interaction: discord.Interaction):
        configs = await self.get_guild_configs(interaction.guild_id)

        if not configs:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} No Configurations Found",
                description="There are no welcome setups configured for this server. Create one using `/create-welcome`.",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        embed = discord.Embed(
            title=f"{EMOJI_TICK} Active Welcome Setups ({len(configs)}/3)",
            color=discord.Color.blue()
        )

        for cfg in configs:
            channel = interaction.guild.get_channel(cfg["channel_id"])
            channel_mention = channel.mention if channel else f"`Deleted Channel ({cfg['channel_id']})`"
            
            embed.add_field(
                name=f"⚙️ Welcome Setup #{cfg['config_id']}",
                value=(
                    f"• **Channel:** {channel_mention}\n"
                    f"• **Title:** `{cfg['title']}`\n"
                    f"• **Banner:** `{'Configured' if cfg.get('banner') else 'None'}`\n"
                    f"• **Ping User:** `{'Yes' if cfg.get('ping_user') else 'No'}`"
                ),
                inline=False
            )

        view = WelcomeManageView(self, interaction.guild_id, interaction.user, configs)
        embed.set_footer(text="Use buttons below to test or clear setups.")
        embed.timestamp = discord.utils.utcnow()

        await interaction.response.send_message(embed=embed, view=view)

    # ==========================================
    # SLASH COMMAND: /delete-welcome
    # ==========================================
    @app_commands.command(
        name="delete-welcome",
        description="Delete a welcome configuration setup by ID (1, 2, or 3)."
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(id="Setup ID (1, 2, or 3) to delete")
    async def delete_welcome(self, interaction: discord.Interaction, id: int):
        async with aiosqlite.connect(DB_FILE) as db:
            cursor = await db.execute(
                "DELETE FROM welcome_setups WHERE guild_id = ? AND config_id = ?",
                (interaction.guild_id, id)
            )
            await db.commit()
            deleted_rows = cursor.rowcount

        if deleted_rows == 0:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Setup Not Found",
                description=f"No welcome setup with ID `#{id}` exists for this server.",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        embed = discord.Embed(
            title=f"{EMOJI_TICK} Welcome Setup Deleted",
            description=f"Successfully deleted Welcome Setup `#{id}`.",
            color=discord.Color.green()
        )
        embed.timestamp = discord.utils.utcnow()
        await interaction.response.send_message(embed=embed)

    # ==========================================
    # SLASH COMMAND: /test-welcome
    # ==========================================
    @app_commands.command(
        name="test-welcome",
        description="Test a welcome message setup preview by ID."
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(id="Setup ID (1, 2, or 3) to test")
    async def test_welcome(self, interaction: discord.Interaction, id: int):
        await self.run_test_setup(interaction, id)

    # ==========================================
    # EVENT LISTENER: AUTOMATED MEMBER JOIN
    # ==========================================
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        configs = await self.get_guild_configs(member.guild.id)
        if not configs:
            return

        for config in configs:
            channel = member.guild.get_channel(config["channel_id"])
            if channel:
                try:
                    welcome_embed = self.build_welcome_embed(config, member, channel)
                    content = member.mention if config.get("ping_user") else None
                    await channel.send(content=content, embed=welcome_embed)
                except Exception:
                    pass

    # ==========================================
    # ERROR HANDLERS
    # ==========================================
    @create_welcome.error
    @list_welcome.error
    @delete_welcome.error
    @test_welcome.error
    async def welcome_error_handler(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Permission Denied",
                description=f"{interaction.user.mention}, you need `Manage Server` permission to configure welcome setups.",
                color=discord.Color.red()
            )
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(WelcomeCog(bot))
      
