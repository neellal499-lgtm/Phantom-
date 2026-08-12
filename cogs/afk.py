import time
import discord
from discord import app_commands
from discord.ext import commands

# Custom Emoji Constants
EMOJI_TICK = "<a:Tick:1536982741537656832>"
EMOJI_CROSS = "<:Cross:1536982744008106055>"

class AFKCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Structure: {user_id: {"reason": str, "time": float, "pings": int, "pinger_ids": list}}
        self.afk_users = {}

    def format_duration(self, start_time: float) -> str:
        """Calculates and formats elapsed time into a readable string."""
        elapsed = int(time.time() - start_time)
        days, remainder = divmod(elapsed, 86400)
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

    # ==========================================
    # SLASH COMMAND: /afk
    # ==========================================
    @app_commands.command(name="afk", description="Set your AFK status with an optional reason.")
    @app_commands.describe(reason="The reason why you are going AFK")
    async def afk_command(self, interaction: discord.Interaction, reason: str = "AFK"):
        user = interaction.user

        # Store AFK data
        self.afk_users[user.id] = {
            "reason": reason,
            "time": time.time(),
            "pings": 0,
            "pinger_ids": []
        }

        # Update server nickname to show [AFK] tag if permissions allow
        if interaction.guild and interaction.guild.me.guild_permissions.manage_nicknames:
            try:
                if not user.display_name.startswith("[AFK]"):
                    await user.edit(nick=f"[AFK] {user.display_name}"[:32])
            except discord.Forbidden:
                pass

        # Build Rich Response Embed
        embed = discord.Embed(
            title=f"{EMOJI_TICK} AFK Status Set",
            description=f"{user.mention}, your AFK status has been successfully updated.",
            color=discord.Color.dark_theme_prime() if hasattr(discord.Color, "dark_theme_prime") else discord.Color.blue()
        )
        embed.add_field(name="Reason", value=f"```\n{reason}\n```", inline=False)
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.set_footer(text=f"User ID: {user.id} • Phantom AFK System", icon_url=self.bot.user.display_avatar.url)
        embed.timestamp = discord.utils.utcnow()

        await interaction.response.send_message(content=user.mention, embed=embed)

    # ==========================================
    # ERROR HANDLING: MissingRequiredArgument
    # ==========================================
    @commands.Cog.listener()
    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Catches missing required argument errors in slash commands."""
        if isinstance(error, app_commands.MissingRequiredArgument):
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Missing Parameter",
                description=f"{interaction.user.mention}, you missed a required argument: `{error.param.name}`.",
                color=discord.Color.red()
            )
            embed.set_footer(text="Please provide all required parameters.")
            
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)

    # ==========================================
    # EVENT LISTENER: Pings & Auto-AFK Removal
    # ==========================================
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore messages sent by bots or outside guilds
        if message.author.bot or not message.guild:
            return

        author_id = message.author.id

        # ----------------------------------------------------
        # 1. CHECK IF THE AUTHOR WAS AFK (REMOVE AFK)
        # ----------------------------------------------------
        if author_id in self.afk_users:
            afk_data = self.afk_users.pop(author_id)
            duration_str = self.format_duration(afk_data["time"])
            ping_count = afk_data["pings"]
            pings_label = "ping" if ping_count == 1 else "pings"

            # Reset user nickname if possible
            if message.guild.me.guild_permissions.manage_nicknames:
                try:
                    if message.author.display_name.startswith("[AFK]"):
                        clean_nick = message.author.display_name.replace("[AFK]", "").strip()
                        await message.author.edit(nick=clean_nick)
                except discord.Forbidden:
                    pass

            embed = discord.Embed(
                title=f"{EMOJI_TICK} Welcome Back!",
                description=f"{message.author.mention}, your AFK status has been removed.",
                color=discord.Color.green()
            )
            embed.add_field(name="Time Elapsed", value=f"`{duration_str}`", inline=True)
            embed.add_field(name="Missed Mentions", value=f"`{ping_count}` {pings_label}", inline=True)
            embed.set_thumbnail(url=message.author.display_avatar.url)
            embed.set_footer(text="AFK System", icon_url=self.bot.user.display_avatar.url)
            embed.timestamp = discord.utils.utcnow()

            await message.channel.send(content=f"{message.author.mention} welcome back!", embed=embed)

        # ----------------------------------------------------
        # 2. CHECK IF A MENTIONED USER IS AFK
        # ----------------------------------------------------
        if message.mentions:
            for mentioned_user in message.mentions:
                if mentioned_user.id in self.afk_users and mentioned_user.id != author_id:
                    afk_info = self.afk_users[mentioned_user.id]
                    afk_info["pings"] += 1
                    afk_info["pinger_ids"].append(author_id)

                    duration_str = self.format_duration(afk_info["time"])
                    reason = afk_info["reason"]

                    embed = discord.Embed(
                        title=f"{EMOJI_CROSS} User is AFK",
                        description=f"{message.author.mention}, the user {mentioned_user.mention} is currently away.",
                        color=discord.Color.orange()
                    )
                    embed.add_field(name="Reason", value=f"```\n{reason}\n```", inline=False)
                    embed.add_field(name="AFK Since", value=f"`{duration_str} ago`", inline=True)
                    embed.set_thumbnail(url=mentioned_user.display_avatar.url)
                    embed.set_footer(text=f"Total Pings Received: {afk_info['pings']}", icon_url=self.bot.user.display_avatar.url)
                    embed.timestamp = discord.utils.utcnow()

                    await message.channel.send(content=f"{message.author.mention}", embed=embed)
                    break

async def setup(bot: commands.Bot):
    await bot.add_cog(AFKCog(bot))
          
