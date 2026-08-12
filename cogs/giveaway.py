import sqlite3
import aiosqlite
import random
import re
import discord
from datetime import datetime, timedelta
from discord import app_commands
from discord.ext import commands, tasks
from typing import Optional, List, Dict

# Custom Emoji Constants
EMOJI_TICK = "<a:Tick:1536982741537656832>"
EMOJI_CROSS = "<:Cross:1536982744008106055>"
DB_FILE = "giveaways.db"


def parse_duration(duration_str: str) -> Optional[timedelta]:
    """Parses time strings like '10m', '1h', '2d' into timedelta objects."""
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


class GiveawayView(discord.ui.View):
    """Interactive control view attached to active giveaway messages."""
    def __init__(self, cog: "GiveawayCog"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Enter / Leave", style=discord.ButtonStyle.primary, emoji="🎉", custom_id="giveaway_entry_btn")
    async def enter_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        message_id = interaction.message.id
        user = interaction.user

        async with aiosqlite.connect(DB_FILE) as db:
            db.row_factory = sqlite3.Row
            async with db.execute("SELECT * FROM giveaways WHERE message_id = ? AND ended = 0", (message_id,)) as cursor:
                g = await cursor.fetchone()

            if not g:
                return await interaction.response.send_message(
                    f"{EMOJI_CROSS} This giveaway has ended or is no longer active.",
                    ephemeral=True
                )

            # Role Requirement Check
            if g["required_role_id"]:
                req_role = interaction.guild.get_role(g["required_role_id"])
                if req_role and req_role not in user.roles:
                    return await interaction.response.send_message(
                        f"{EMOJI_CROSS} You need the {req_role.mention} role to enter this giveaway.",
                        ephemeral=True
                    )

            # Account Age Check (Days)
            if g["min_account_age_days"] > 0:
                acc_age = (discord.utils.utcnow() - user.created_at).days
                if acc_age < g["min_account_age_days"]:
                    return await interaction.response.send_message(
                        f"{EMOJI_CROSS} Your account must be at least `{g['min_account_age_days']} days` old to enter.",
                        ephemeral=True
                    )

            raw_entries = g["entries"] or ""
            entry_list = [int(u) for u in raw_entries.split(",") if u.isdigit()]

            if user.id in entry_list:
                # Remove entry (Toggle off)
                entry_list.remove(user.id)
                new_entries_str = ",".join(str(u) for u in entry_list)
                await db.execute("UPDATE giveaways SET entries = ? WHERE message_id = ?", (new_entries_str, message_id))
                await db.commit()

                await interaction.response.send_message("❌ You have left the giveaway.", ephemeral=True)
            else:
                # Calculate bonus entries
                entry_weight = 1
                if g["bonus_role_id"]:
                    bonus_role = interaction.guild.get_role(g["bonus_role_id"])
                    if bonus_role and bonus_role in user.roles:
                        entry_weight = g["bonus_multiplier"] or 2

                # Add user entries weighted by bonus multiplier
                for _ in range(entry_weight):
                    entry_list.append(user.id)

                new_entries_str = ",".join(str(u) for u in entry_list)
                await db.execute("UPDATE giveaways SET entries = ? WHERE message_id = ?", (new_entries_str, message_id))
                await db.commit()

                bonus_msg = f" (Includes `{entry_weight}x` bonus entries!)" if entry_weight > 1 else ""
                await interaction.response.send_message(
                    f"{EMOJI_TICK} You entered the giveaway! Good luck!{bonus_msg}",
                    ephemeral=True
                )

        # Update Footer Stats
        try:
            unique_entries = len(set(entry_list))
            embed = interaction.message.embeds[0]
            embed.set_footer(text=f"Total Entries: {unique_entries} • Active")
            await interaction.message.edit(embed=embed)
        except Exception:
            pass

    @discord.ui.button(label="Entry Info", style=discord.ButtonStyle.secondary, emoji="📊", custom_id="giveaway_info_btn")
    async def info_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        message_id = interaction.message.id

        async with aiosqlite.connect(DB_FILE) as db:
            db.row_factory = sqlite3.Row
            async with db.execute("SELECT * FROM giveaways WHERE message_id = ?", (message_id,)) as cursor:
                g = await cursor.fetchone()

        if not g:
            return await interaction.response.send_message(f"{EMOJI_CROSS} Giveaway record not found.", ephemeral=True)

        raw_entries = g["entries"] or ""
        entry_list = [int(u) for u in raw_entries.split(",") if u.isdigit()]
        user_entries = entry_list.count(interaction.user.id)
        total_tickets = len(entry_list)

        chance = round((user_entries / total_tickets) * 100, 2) if total_tickets > 0 else 0.0

        embed = discord.Embed(
            title=f"📊 Giveaway Stats — {g['prize']}",
            color=discord.Color.blue()
        )
        embed.add_field(name="Your Entered Tickets", value=f"`{user_entries}`", inline=True)
        embed.add_field(name="Total Ticket Pool", value=f"`{total_tickets}`", inline=True)
        embed.add_field(name="Winning Probability", value=f"`{chance}%`", inline=True)

        if g["required_role_id"]:
            role = interaction.guild.get_role(g["required_role_id"])
            embed.add_field(name="Required Role", value=role.mention if role else "`None`", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)


class GiveawayCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.giveaway_check.start()

    def cog_unload(self):
        self.giveaway_check.cancel()

    async def cog_load(self):
        """Initializes database schema and registers persistent UI view."""
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS giveaways (
                    message_id INTEGER PRIMARY KEY,
                    channel_id INTEGER,
                    guild_id INTEGER,
                    host_id INTEGER,
                    prize TEXT,
                    winner_count INTEGER,
                    end_time TEXT,
                    entries TEXT,
                    required_role_id INTEGER,
                    bonus_role_id INTEGER,
                    bonus_multiplier INTEGER,
                    min_account_age_days INTEGER,
                    ended INTEGER DEFAULT 0
                )
            """)
            await db.commit()

        self.bot.add_view(GiveawayView(self))

    # ==========================================
    # BACKGROUND TASK: GIVEAWAY TIMER CHECK
    # ==========================================
    @tasks.loop(seconds=15)
    async def giveaway_check(self):
        """Monitors active giveaways and resolves ended ones."""
        now = discord.utils.utcnow()
        async with aiosqlite.connect(DB_FILE) as db:
            db.row_factory = sqlite3.Row
            async with db.execute("SELECT * FROM giveaways WHERE ended = 0") as cursor:
                active_giveaways = await cursor.fetchall()

            for g in active_giveaways:
                end_dt = datetime.fromisoformat(g["end_time"])
                if now >= end_dt:
                    await self.finish_giveaway(dict(g))

    @giveaway_check.before_loop
    async def before_giveaway_check(self):
        await self.bot.wait_until_ready()

    async def finish_giveaway(self, giveaway_data: dict):
        """Picks winners, notifies via DMs, and posts results."""
        message_id = giveaway_data["message_id"]

        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("UPDATE giveaways SET ended = 1 WHERE message_id = ?", (message_id,))
            await db.commit()

        guild = self.bot.get_guild(giveaway_data["guild_id"])
        if not guild:
            return

        channel = guild.get_channel(giveaway_data["channel_id"])
        if not channel:
            return

        try:
            msg = await channel.fetch_message(message_id)
        except Exception:
            return

        raw_entries = giveaway_data["entries"] or ""
        entry_list = [int(u) for u in raw_entries.split(",") if u.isdigit()]

        winner_count = giveaway_data["winner_count"]
        prize = giveaway_data["prize"]

        if not entry_list:
            embed = discord.Embed(
                title=f"🎉 GIVEAWAY ENDED — {prize}",
                description="Giveaway ended with **no valid entries**.",
                color=discord.Color.dark_gray()
            )
            embed.set_footer(text="Giveaway Completed")
            embed.timestamp = discord.utils.utcnow()
            await msg.edit(embed=embed, view=None)
            return await channel.send(f"⚠️ The giveaway for **{prize}** ended, but there were no entries.")

        # Deduplicate entry list while maintaining weighted probability
        unique_winner_ids = list(set(random.sample(entry_list, min(len(set(entry_list)), winner_count))))
        winners_mentions = [f"<@{uid}>" for uid in unique_winner_ids]

        embed = discord.Embed(
            title=f"🎉 GIVEAWAY ENDED — {prize}",
            description=f"• **Winners:** {', '.join(winners_mentions)}\n• **Host:** <@{giveaway_data['host_id']}>\n• **Total Unique Entries:** `{len(set(entry_list))}`",
            color=discord.Color.gold()
        )
        embed.set_footer(text="Giveaway Completed")
        embed.timestamp = discord.utils.utcnow()

        await msg.edit(embed=embed, view=None)
        await channel.send(
            content=f"🎉 Congratulations {', '.join(winners_mentions)}! You won **{prize}**!"
        )

        # Send DM Notifications to winners
        for uid in unique_winner_ids:
            winner_user = guild.get_member(uid)
            if winner_user:
                try:
                    dm_embed = discord.Embed(
                        title=f"{EMOJI_TICK} YOU WON A GIVEAWAY!",
                        description=f"You won **{prize}** in **{guild.name}**!",
                        color=discord.Color.gold()
                    )
                    dm_embed.add_field(name="Claim Instructions", value="Contact the giveaway host or open a support ticket to claim your prize.", inline=False)
                    await winner_user.send(embed=dm_embed)
                except Exception:
                    pass

    # ==========================================
    # SLASH COMMAND: /gstart
    # ==========================================
    @app_commands.command(
        name="gstart",
        description="Start an advanced interactive giveaway with role requirements and multipliers."
    )
    @app_commands.checks.has_permissions(manage_events=True)
    @app_commands.describe(
        duration="Duration of the giveaway (e.g. 10m, 1h, 2d)",
        winners="Number of winners to select",
        prize="The prize being given away",
        required_role="Optional: Role required to enter this giveaway",
        bonus_role="Optional: Role that earns extra bonus entries",
        bonus_multiplier="Bonus multiplier for bonus role holders (Default: 2x)",
        min_account_age="Optional: Minimum account age in days to enter",
        channel="Optional target channel (Defaults to current channel)"
    )
    async def gstart_command(
        self,
        interaction: discord.Interaction,
        duration: str,
        winners: int,
        prize: str,
        required_role: Optional[discord.Role] = None,
        bonus_role: Optional[discord.Role] = None,
        bonus_multiplier: Optional[int] = 2,
        min_account_age: Optional[int] = 0,
        channel: Optional[discord.TextChannel] = None
    ):
        target_channel = channel or interaction.channel

        duration_delta = parse_duration(duration)
        if not duration_delta:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Invalid Duration",
                description="Please use valid duration formatting:\n• `10m` = 10 Minutes\n• `1h` = 1 Hour\n• `2d` = 2 Days",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        if winners < 1 or winners > 20:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Invalid Winner Count",
                description="Winner count must be between **1** and **20**.",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        end_time = discord.utils.utcnow() + duration_delta

        embed = discord.Embed(
            title=f"🎉 GIVEAWAY — {prize}",
            description=(
                f"Click the button below to enter!\n\n"
                f"• **Winners:** `{winners}`\n"
                f"• **Ends:** <t:{int(end_time.timestamp())}:R> (<t:{int(end_time.timestamp())}:f>)\n"
                f"• **Host:** {interaction.user.mention}\n"
            ),
            color=discord.Color.blue()
        )

        if required_role:
            embed.add_field(name="🔒 Required Role", value=required_role.mention, inline=True)
        if bonus_role:
            embed.add_field(name="⚡ Bonus Role", value=f"{bonus_role.mention} (`{bonus_multiplier}x Entries`)", inline=True)
        if min_account_age > 0:
            embed.add_field(name="🛡️ Min Account Age", value=f"`{min_account_age} Days`", inline=True)

        embed.set_footer(text="Total Entries: 0 • Active")
        embed.timestamp = end_time

        view = GiveawayView(self)
        msg = await target_channel.send(embed=embed, view=view)

        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("""
                INSERT INTO giveaways 
                (message_id, channel_id, guild_id, host_id, prize, winner_count, end_time, entries, required_role_id, bonus_role_id, bonus_multiplier, min_account_age_days, ended)
                VALUES (?, ?, ?, ?, ?, ?, ?, '', ?, ?, ?, ?, 0)
            """, (
                msg.id, target_channel.id, interaction.guild_id, interaction.user.id,
                prize, winners, end_time.isoformat(),
                required_role.id if required_role else None,
                bonus_role.id if bonus_role else None,
                bonus_multiplier, min_account_age
            ))
            await db.commit()

        resp_embed = discord.Embed(
            title=f"{EMOJI_TICK} Giveaway Started",
            description=f"Giveaway for **{prize}** created in {target_channel.mention}.",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=resp_embed, ephemeral=True)

    # ==========================================
    # SLASH COMMAND: /gend
    # ==========================================
    @app_commands.command(
        name="gend",
        description="End an active giveaway immediately and pick winners."
    )
    @app_commands.checks.has_permissions(manage_events=True)
    @app_commands.describe(message_id="The Message ID of the active giveaway")
    async def gend_command(self, interaction: discord.Interaction, message_id: str):
        if not message_id.isdigit():
            embed = discord.Embed(title=f"{EMOJI_CROSS} Invalid ID", description="Message ID must be numeric.", color=discord.Color.red())
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        msg_id = int(message_id)
        async with aiosqlite.connect(DB_FILE) as db:
            db.row_factory = sqlite3.Row
            async with db.execute("SELECT * FROM giveaways WHERE message_id = ? AND ended = 0", (msg_id,)) as cursor:
                g = await cursor.fetchone()

        if not g:
            embed = discord.Embed(title=f"{EMOJI_CROSS} Not Found", description="No active giveaway found with that Message ID.", color=discord.Color.red())
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        await self.finish_giveaway(dict(g))
        embed = discord.Embed(title=f"{EMOJI_TICK} Giveaway Ended", description=f"Successfully ended giveaway `#{msg_id}`.", color=discord.Color.green())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ==========================================
    # SLASH COMMAND: /greroll
    # ==========================================
    @app_commands.command(
        name="greroll",
        description="Re-roll new winners for a completed giveaway."
    )
    @app_commands.checks.has_permissions(manage_events=True)
    @app_commands.describe(message_id="The Message ID of the completed giveaway")
    async def greroll_command(self, interaction: discord.Interaction, message_id: str):
        if not message_id.isdigit():
            embed = discord.Embed(title=f"{EMOJI_CROSS} Invalid ID", description="Message ID must be numeric.", color=discord.Color.red())
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        msg_id = int(message_id)
        async with aiosqlite.connect(DB_FILE) as db:
            db.row_factory = sqlite3.Row
            async with db.execute("SELECT * FROM giveaways WHERE message_id = ? AND ended = 1", (msg_id,)) as cursor:
                g = await cursor.fetchone()

        if not g:
            embed = discord.Embed(title=f"{EMOJI_CROSS} Not Found", description="No finished giveaway found with that Message ID.", color=discord.Color.red())
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        raw_entries = g["entries"] or ""
        entry_list = [int(u) for u in raw_entries.split(",") if u.isdigit()]

        if not entry_list:
            embed = discord.Embed(title=f"{EMOJI_CROSS} No Entries", description="Cannot reroll: there were no entries in this giveaway.", color=discord.Color.red())
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        unique_winner_ids = list(set(random.sample(entry_list, min(len(set(entry_list)), g["winner_count"]))))
        winners_mentions = [f"<@{uid}>" for uid in unique_winner_ids]

        channel = interaction.guild.get_channel(g["channel_id"])
        if channel:
            await channel.send(f"🎲 **REROLL:** New winner(s) for **{g['prize']}**: {', '.join(winners_mentions)}!")

        embed = discord.Embed(title=f"{EMOJI_TICK} Winners Rerolled", description=f"Picked new winners: {', '.join(winners_mentions)}", color=discord.Color.green())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ==========================================
    # ERROR HANDLING
    # ==========================================
    @gstart_command.error
    @gend_command.error
    @greroll_command.error
    async def giveaway_error_handler(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Permission Denied",
                description=f"{interaction.user.mention}, you need `Manage Events` permission.",
                color=discord.Color.red()
            )
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(GiveawayCog(bot))
