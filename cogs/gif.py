import os
import aiohttp
import random
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

# Custom Emoji Constants
EMOJI_TICK = "<a:Tick:1536982741537656832>"
EMOJI_CROSS = "<:Cross:1536982744008106055>"

# Fetch key from Railway environment variables (falls back to default public key if not set)
TENOR_API_KEY = os.getenv("TENOR_API_KEY", "LIVDSRZULEPB")


class GifCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def fetch_tenor_gif(self, query: str) -> Optional[str]:
        """Queries the Tenor API and returns a direct GIF URL."""
        url = "https://g.tenor.com/v1/search"
        params = {
            "q": query,
            "key": TENOR_API_KEY,
            "limit": 15,
            "contentfilter": "medium"
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                results = data.get("results", [])

                if not results:
                    return None

                # Choose a random top result for variety
                selected = random.choice(results)
                try:
                    return selected["media"][0]["gif"]["url"]
                except (KeyError, IndexError):
                    return None

    # ==========================================
    # SLASH COMMAND: /gif
    # ==========================================
    @app_commands.command(
        name="gif",
        description="Find and post a GIF based on your description, mentioning a member."
    )
    @app_commands.describe(
        search="Description of the GIF you want to find (e.g., happy dance, anime wave)",
        user="Optional member to mention in the GIF post"
    )
    async def gif_command(
        self,
        interaction: discord.Interaction,
        search: str,
        user: Optional[discord.Member] = None
    ):
        await interaction.response.defer()

        gif_url = await self.fetch_tenor_gif(search)

        if not gif_url:
            embed = discord.Embed(
                title=f"{EMOJI_CROSS} No GIF Found",
                description=f"Could not find any GIFs matching `{search}`. Try another search term!",
                color=discord.Color.red()
            )
            return await interaction.followup.send(embed=embed, ephemeral=True)

        target_mention = user.mention if user else interaction.user.mention
        message_content = f"🎬 {target_mention}, here is a GIF for **{search}** (from {interaction.user.mention}):"

        embed = discord.Embed(
            title=f"Search Result: {search.title()}",
            color=discord.Color.blue()
        )
        embed.set_image(url=gif_url)
        embed.set_footer(text=f"Requested by {interaction.user} • Powered by Tenor", icon_url=interaction.user.display_avatar.url)
        embed.timestamp = discord.utils.utcnow()

        await interaction.followup.send(content=message_content, embed=embed)

    # ==========================================
    # ERROR HANDLING
    # ==========================================
    @gif_command.error
    async def gif_error_handler(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        embed = discord.Embed(
            title=f"{EMOJI_CROSS} Error Fetching GIF",
            description=f"An error occurred while processing your request: `{str(error)}`",
            color=discord.Color.red()
        )
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(GifCog(bot))
