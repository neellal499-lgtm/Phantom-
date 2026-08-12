import asyncio
import sqlite3
import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, List

# Custom Emoji Constants
EMOJI_TICK = "<a:Tick:1536982741537656832>"
EMOJI_CROSS = "<:Cross:1536982744008106055>"
DB_FILE = "autorole.db"


class AutoRoleDashboardView(discord.ui.View):
    """Interactive management dashboard for server auto-role settings."""
    def __init__(self, cog: "AutoRoleCog", guild_id: int, author: discord.Member):
        super().__init__(timeout=120)
        self.cog = cog
        self.guild_id = guild_id
        self.author = author

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                f"{EMOJI_CROSS} Only {self.author.mention} can interact with these controls.",
                ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Refresh Status", style=discord.ButtonStyle.primary, emoji="🔁")
    async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = await self.cog.get_guild_config(self.guild_id)
        embed = self.cog.build_status_embed(interaction.guild, config)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Test On Self", style=discord.ButtonStyle.secondary, emoji="🧪")
    async def test_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = await self.cog.get_guild_config(self.guild_id)
        if not config or not config["human_roles"]:
            return await interaction.response.send_message(
                f"{EMOJI_CROSS} No human auto-roles configured to test.",
                ephemeral=True
            )

        guild = interaction.guild
        assigned_roles = []
        failed_roles = []

        for role_id in config["human_roles"]:
            role = guild.get_role(role_id)
            if role:
                try:
                    await interaction.user.add_roles(role, reason="Auto-Role Self Test")
                    assigned_roles.append(role.mention)
                except Exception:
                    failed_roles.append(f"`{role.name}`")

        msg = f"{EMOJI_TICK} Assigned: {', '.join(assigned_roles)}" if assigned_roles else "No roles assigned."
        if failed_roles:
            msg += f"\n{EMOJI_CROSS} Failed: {', '.join(failed_roles)}"

        await interaction.response.send_message(content=msg, ephemeral=True)

    @discord.ui.button(label="Clear Config", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def clear_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("DELETE FROM autorole_config WHERE guild_id = ?", (self.guild_id,))
            await db.commit()

        embed = discord.Embed(
            title=f"{EMOJI_TICK} Configuration Wiped",
            description="Auto-role configuration for this server has been cleared.",
            color=discord.Color.green()
        )
        await interaction.response.edit_message(embed=embed, view=None)


class AutoRoleCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        """Initializes database schema on cog load."""
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS autorole_config (
                    guild_id INTEGER PRIMARY KEY,
                    human_roles TEXT,
                    bot_role INTEGER,
                    delay_seconds INTEGER DEFAULT 0,
                    updated_by INTEGER,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.commit()

    async def get_guild_config(self, guild_id: int) -> Optional[dict]:
        """Fetches auto-role configuration settings for a guild."""
        async with aiosqlite.connect(DB_FILE) as db:
            db.row_factory = sqlite3.Row
            async with db.execute(
                "SELECT * FROM autorole_config WHERE guild_id = ?",
                (guild_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                
                raw_human_roles = row["human_roles"] or ""
                human_role_ids = [int(r) for r in raw_human_roles.split(",") if r.isdigit()]
                
                return {
                    "guild_id": row["guild_id"],
                    "human_roles": human_role_ids,
                    "bot_role": row["bot_role"],
                    "delay_seconds": row["delay_seconds"],
                    "updated_by": row["updated_by"]
                }

    def build_status_embed(self, guild: discord.Guild, config: Optional[dict]) -> discord.Embed:
        """Helper to format status embeds."""
        if not config:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} No Auto-Role Configured",
                description=f"Auto-role is currently **disabled** on **{guild.name}**.\nUse `/autorole-add` to set up automated role assignments.",
                color=discord.Color.red()
            )
            return embed

        human_roles_mentions = []
        for rid in config["human_roles"]:
            role = guild.get_role(rid)
            human_roles_mentions.append(role.mention if role else f"`Deleted Role ({rid})`")

        human_display = "\n".join([f"• {m}" for m in human_roles_mentions]) or "`None`"

        bot_role_obj = guild.get_role(config["bot_role"]) if config["bot_role"] else None
        bot_display = bot_role_obj.mention if bot_role_obj else "`None`"

        delay_display = f"`{config['delay_seconds']}s`" if config["delay_seconds"] > 0 else "`Immediate`"

        embed = discord.Embed(
            title=f"{EMOJI_TICK} Auto-Role System Configuration",
            description=f"Current automated role onboarding rules for **{guild.name}**:",
            color=discord.Color.blue()
        )
        embed.add_field(name="👥 Human Member Roles", value=human_display, inline=False)
        embed.add_field(name="🤖 Bot Specific Role", value=bot_display, inline=True)
        embed.add_field(name="⏱️ Assignment Delay", value=delay_display, inline=True)

        embed.set_footer(text=f"Server ID: {guild.id} • Phantom Onboarding Matrix", icon_url=self.bot.user.display_avatar.url)
        embed.timestamp = discord.utils.utcnow()
        return embed

    # ==========================================
    # SLASH COMMAND: /autorole-add
    # ==========================================
    @app_commands.command(
        name="autorole-add",
        description="Add a role to the automatic member join assignment list (Max 5 roles)."
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    @app_commands.bot_has_permissions(manage_roles=True)
    @app_commands.describe(
        role="The role to automatically grant to new human members",
        is_bot_role="Set True if this role should only be assigned to joining Discord Bots"
    )
    async def autorole_add_command(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        is_bot_role: bool = False
    ):
        guild = interaction.guild
        moderator = interaction.user

        # Validation Checks
        if role.is_default():
            embed = discord.Embed(title=f"{EMOJI_CROSS} Invalid Role", description="You cannot assign `@everyone`.", color=discord.Color.red())
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        if role.is_integration() or role.is_bot_managed():
            embed = discord.Embed(title=f"{EMOJI_CROSS} Managed Role", description="This role is managed by an integration and cannot be assigned.", color=discord.Color.red())
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        if role >= moderator.top_role and moderator.id != guild.owner_id:
            embed = discord.Embed(title=f"{EMOJI_CROSS} Hierarchy Error", description=f"Role {role.mention} is equal to or higher than your top role.", color=discord.Color.red())
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        if role >= guild.me.top_role:
            embed = discord.Embed(title=f"{EMOJI_CROSS} Hierarchy Error", description=f"I cannot assign {role.mention} because it is equal to or higher than my top role.", color=discord.Color.red())
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        config = await self.get_guild_config(guild.id)
        human_roles = config["human_roles"] if config else []
        bot_role = config["bot_role"] if config else None
        delay = config["delay_seconds"] if config else 0

        if is_bot_role:
            bot_role = role.id
        else:
            if role.id in human_roles:
                embed = discord.Embed(title=f"{EMOJI_CROSS} Duplicate Role", description=f"{role.mention} is already in the auto-role list.", color=discord.Color.red())
                return await interaction.response.send_message(embed=embed, ephemeral=True)
            if len(human_roles) >= 5:
                embed = discord.Embed(title=f"{EMOJI_CROSS} Limit Reached", description="You can configure a maximum of **5 human auto-roles**.", color=discord.Color.red())
                return await interaction.response.send_message(embed=embed, ephemeral=True)
            human_roles.append(role.id)

        roles_str = ",".join(str(r) for r in human_roles)

        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("""
                INSERT OR REPLACE INTO autorole_config (guild_id, human_roles, bot_role, delay_seconds, updated_by)
                VALUES (?, ?, ?, ?, ?)
            """, (guild.id, roles_str, bot_role, delay, moderator.id))
            await db.commit()

        embed = discord.Embed(
            title=f"{EMOJI_TICK} Auto-Role Added",
            description=f"Successfully added {role.mention} to the {'bot' if is_bot_role else 'human'} auto-role queue.",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)

    # ==========================================
    # SLASH COMMAND: /autorole-delay
    # ==========================================
    @app_commands.command(
        name="autorole-delay",
        description="Configure a delay timer before auto-roles are assigned to new members."
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    @app_commands.describe(seconds="Delay in seconds before assigning roles (0 to 600 seconds)")
    async def autorole_delay_command(self, interaction: discord.Interaction, seconds: int):
        if seconds < 0 or seconds > 600:
            embed = discord.Embed(title=f"{EMOJI_CROSS} Invalid Range", description="Delay must be between `0` and `600` seconds (10 minutes).", color=discord.Color.red())
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        config = await self.get_guild_config(interaction.guild_id)
        if not config:
            embed = discord.Embed(title=f"{EMOJI_CROSS} Setup Required", description="Set up at least one auto-role first using `/autorole-add`.", color=discord.Color.red())
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        roles_str = ",".join(str(r) for r in config["human_roles"])

        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("""
                UPDATE autorole_config SET delay_seconds = ? WHERE guild_id = ?
            """, (seconds, interaction.guild_id))
            await db.commit()

        embed = discord.Embed(
            title=f"{EMOJI_TICK} Delay Timer Updated",
            description=f"Auto-roles will now be assigned **{seconds} seconds** after a member joins.",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)

    # ==========================================
    # SLASH COMMAND: /autorole-status
    # ==========================================
    @app_commands.command(
        name="autorole-status",
        description="Inspect and manage current server auto-role settings."
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    async def autorole_status_command(self, interaction: discord.Interaction):
        config = await self.get_guild_config(interaction.guild_id)
        embed = self.build_status_embed(interaction.guild, config)
        view = AutoRoleDashboardView(self, interaction.guild_id, interaction.user)
        await interaction.response.send_message(embed=embed, view=view)

    # ==========================================
    # EVENT LISTENER: AUTOMATED MEMBER JOIN
    # ==========================================
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        config = await self.get_guild_config(guild.id)

        if not config:
            return

        # Handle delay timer
        delay = config.get("delay_seconds", 0)
        if delay > 0:
            await asyncio.sleep(delay)

        # Re-check if member is still in guild after delay
        if guild.get_member(member.id) is None:
            return

        roles_to_add = []

        if member.bot:
            if config["bot_role"]:
                role = guild.get_role(config["bot_role"])
                if role and role < guild.me.top_role:
                    roles_to_add.append(role)
        else:
            for rid in config["human_roles"]:
                role = guild.get_role(rid)
                if role and role < guild.me.top_role:
                    roles_to_add.append(role)

        if roles_to_add and guild.me.guild_permissions.manage_roles:
            try:
                await member.add_roles(*roles_to_add, reason="Automated Auto-Role Onboarding")
            except Exception:
                pass

    # ==========================================
    # ERROR HANDLING
    # ==========================================
    @autorole_add_command.error
    @autorole_delay_command.error
    @autorole_status_command.error
    async def autorole_error_handler(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Permission Denied",
                description=f"{interaction.user.mention}, you need `Manage Roles` permission.",
                color=discord.Color.red()
            )
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoRoleCog(bot))
      
