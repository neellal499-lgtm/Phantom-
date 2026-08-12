import os
import sqlite3
import aiosqlite
import aiohttp
import random
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, List

# Custom Emoji Constants
EMOJI_TICK = "<a:Tick:1536982741537656832>"
EMOJI_CROSS = "<:Cross:1536982744008106055>"
DB_FILE = "gif.db"

# Fetch GIPHY API key from Railway environment variables (with public fallback)
GIPHY_API_KEY = os.getenv("GIPHY_API_KEY", "dc6zaTOxFJmzC")

# Preset Social Reactions
REACTION_TYPES = [
    "hug", "slap", "pat", "kiss", "dance", 
    "laugh", "cry", "wave", "highfive", "punch", "blush", "nod"
]


class GifControlView(discord.ui.View):
    """Interactive button controls for navigating, shuffling, and saving GIFs."""
    def __init__(self, cog: "GifCog", query: str, rating: str, target_user: Optional[discord.Member], author: discord.Member):
        super().__init__(timeout=120)
        self.cog = cog
        self.query = query
        self.rating = rating
        self.target_user = target_user
        self.author = author

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                f"{EMOJI_CROSS} Only {self.author.mention} can use these controls.",
                ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Shuffle", style=discord.ButtonStyle.primary, emoji="🔀")
    async def shuffle_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Fetches a new random GIF for the same search term."""
        await interaction.response.defer()
        gif_url = await self.cog.fetch_giphy_gif(query=self.query, rating=self.rating)

        if not gif_url:
            return await interaction.followup.send(f"{EMOJI_CROSS} Could not fetch another GIF for `{self.query}`.", ephemeral=True)

        embed = interaction.message.embeds[0]
        embed.set_image(url=gif_url)
        await interaction.message.edit(embed=embed, view=self)

    @discord.ui.button(label="Save Favorite", style=discord.ButtonStyle.secondary, emoji="⭐")
    async def save_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Saves current GIF to user's personal database favorites."""
        try:
            current_embed = interaction.message.embeds[0]
            gif_url = current_embed.image.url
        except (IndexError, AttributeError):
            return await interaction.response.send_message(f"{EMOJI_CROSS} Could not extract GIF URL.", ephemeral=True)

        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("""
                INSERT INTO user_favorites (user_id, gif_url, tag)
                VALUES (?, ?, ?)
            """, (interaction.user.id, gif_url, self.query[:30]))
            await db.commit()

        embed = discord.Embed(
            title=f"{EMOJI_TICK} Saved to Favorites",
            description=f"Saved this GIF under tag `{self.query[:30]}` to your personal library!",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def delete_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Deletes the posted GIF message."""
        await interaction.message.delete()


class GifCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        """Initializes SQLite database schema for user favorite GIFs."""
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS user_favorites (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    gif_url TEXT,
                    tag TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.commit()

    async def fetch_giphy_gif(self, query: str, rating: str = "pg-13") -> Optional[str]:
        """Queries the GIPHY API search endpoint and returns a direct GIF URL."""
        url = "https://api.giphy.com/v1/gifs/search"
        params = {
            "q": query,
            "api_key": GIPHY_API_KEY,
            "limit": 25,
            "rating": rating
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                results = data.get("data", [])

                if not results:
                    return None

                selected = random.choice(results)
                try:
                    return selected["images"]["original"]["url"]
                except (KeyError, IndexError):
                    return None

    async def fetch_giphy_trending(self, rating: str = "pg-13") -> Optional[str]:
        """Queries the GIPHY API trending endpoint."""
        url = "https://api.giphy.com/v1/gifs/trending"
        params = {
            "api_key": GIPHY_API_KEY,
            "limit": 25,
            "rating": rating
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                results = data.get("data", [])

                if not results:
                    return None

                selected = random.choice(results)
                try:
                    return selected["images"]["original"]["url"]
                except (KeyError, IndexError):
                    return None

    # ==========================================
    # SLASH COMMAND GROUP: /gif
    # ==========================================
    gif_group = app_commands.Group(name="gif", description="Search, send, and save animated GIFs.")

    # ------------------------------------------
    # SUBCOMMAND: /gif search
    # ------------------------------------------
    @gif_group.command(name="search", description="Search and post a GIF based on your keyword query.")
    @app_commands.describe(
        query="Description or keyword (e.g. happy dance, anime wave)",
        user="Optional member to mention in the GIF post",
        rating="Content rating filter (Default: PG-13)"
    )
    @app_commands.choices(rating=[
        app_commands.Choice(name="G (General Audiences)", value="g"),
        app_commands.Choice(name="PG (Parental Guidance)", value="pg"),
        app_commands.Choice(name="PG-13 (Parents Strongly Cautioned)", value="pg-13"),
        app_commands.Choice(name="R (Restricted)", value="r")
    ])
    async def gif_search(
        self,
        interaction: discord.Interaction,
        query: str,
        user: Optional[discord.Member] = None,
        rating: Optional[app_commands.Choice[str]] = None
    ):
        await interaction.response.defer()
        selected_rating = rating.value if rating else "pg-13"

        gif_url = await self.fetch_giphy_gif(query=query, rating=selected_rating)

        if not gif_url:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} No GIF Found",
                description=f"Could not find any GIFs matching `{query}`. Try another search term!",
                color=discord.Color.red()
            )
            return await interaction.followup.send(embed=embed, ephemeral=True)

        target_mention = user.mention if user else interaction.user.mention
        message_content = f"🎬 {target_mention}, here is a GIF for **{query}** (from {interaction.user.mention}):"

        embed = discord.Embed(
            title=f"Search Result: {query.title()}",
            color=discord.Color.blue()
        )
        embed.set_image(url=gif_url)
        embed.set_footer(
            text=f"Requested by {interaction.user} • Powered by GIPHY",
            icon_url=interaction.user.display_avatar.url
        )
        embed.timestamp = discord.utils.utcnow()

        view = GifControlView(self, query, selected_rating, user, interaction.user)
        await interaction.followup.send(content=message_content, embed=embed, view=view)

    # ------------------------------------------
    # SUBCOMMAND: /gif reaction
    # ------------------------------------------
    @gif_group.command(name="reaction", description="Send an expressive anime/social reaction GIF.")
    @app_commands.describe(
        action="The reaction action to perform",
        user="Target member to react towards"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name=act.title(), value=act) for act in REACTION_TYPES
    ])
    async def gif_reaction(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        user: Optional[discord.Member] = None
    ):
        await interaction.response.defer()
        action_name = action.value
        search_query = f"anime {action_name}"

        gif_url = await self.fetch_giphy_gif(query=search_query, rating="pg-13")

        if not gif_url:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Reaction Failed",
                description=f"Could not load reaction GIF for `{action_name}`.",
                color=discord.Color.red()
            )
            return await interaction.followup.send(embed=embed, ephemeral=True)

        if user and user.id != interaction.user.id:
            msg_text = f"✨ {interaction.user.mention} **{action_name}s** {user.mention}!"
        else:
            msg_text = f"✨ {interaction.user.mention} **{action_name}s**!"

        embed = discord.Embed(
            title=f"Reaction — {action_name.title()}",
            color=discord.Color.purple()
        )
        embed.set_image(url=gif_url)
        embed.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
        embed.timestamp = discord.utils.utcnow()

        view = GifControlView(self, search_query, "pg-13", user, interaction.user)
        await interaction.followup.send(content=msg_text, embed=embed, view=view)

    # ------------------------------------------
    # SUBCOMMAND: /gif trending
    # ------------------------------------------
    @gif_group.command(name="trending", description="Fetch real-time top trending GIFs.")
    async def gif_trending(self, interaction: discord.Interaction):
        await interaction.response.defer()

        gif_url = await self.fetch_giphy_trending(rating="pg-13")

        if not gif_url:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} Error",
                description="Could not fetch trending GIFs at this moment.",
                color=discord.Color.red()
            )
            return await interaction.followup.send(embed=embed, ephemeral=True)

        embed = discord.Embed(
            title="🔥 Top Trending GIF",
            color=discord.Color.gold()
        )
        embed.set_image(url=gif_url)
        embed.set_footer(text=f"Requested by {interaction.user} • Powered by GIPHY", icon_url=interaction.user.display_avatar.url)
        embed.timestamp = discord.utils.utcnow()

        view = GifControlView(self, "trending", "pg-13", None, interaction.user)
        await interaction.followup.send(embed=embed, view=view)

    # ------------------------------------------
    # SUBCOMMAND: /gif favorite
    # ------------------------------------------
    @gif_group.command(name="favorite", description="Access and post from your saved favorite GIFs library.")
    async def gif_favorite(self, interaction: discord.Interaction):
        async with aiosqlite.connect(DB_FILE) as db:
            db.row_factory = sqlite3.Row
            async with db.execute(
                "SELECT * FROM user_favorites WHERE user_id = ? ORDER BY created_at DESC",
                (interaction.user.id,)
            ) as cursor:
                favs = await cursor.fetchall()

        if not favs:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} No Favorites Saved",
                description="You haven't saved any favorite GIFs yet!\nClick the ⭐ **Save Favorite** button on any `/gif search` result to build your collection.",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        selected_fav = random.choice(favs)

        embed = discord.Embed(
            title=f"⭐ Favorite GIF — {selected_fav['tag'].title()}",
            description=f"Saved GIF from {interaction.user.mention}'s collection ({len(favs)} total saved).",
            color=discord.Color.gold()
        )
        embed.set_image(url=selected_fav["gif_url"])
        embed.set_footer(text=f"Collection of {interaction.user}", icon_url=interaction.user.display_avatar.url)
        embed.timestamp = discord.utils.utcnow()

        await interaction.response.send_message(embed=embed)

    # ==========================================
    # ERROR HANDLING
    # ==========================================
    @gif_search.error
    @gif_reaction.error
    @gif_trending.error
    @gif_favorite.error
    async def gif_error_handler(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        embed = discord.Embed(
            title=f"{EMOJI_CROSS} Command Error",
            description=f"An error occurred while running GIF command: `{str(error)}`",
            color=discord.Color.red()
        )
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(GifCog(bot))
                
