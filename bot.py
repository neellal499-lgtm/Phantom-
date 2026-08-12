import os
import sys
import logging
import traceback
import asyncio
import discord
from discord.ext import commands, tasks

# ==========================================
# LOGGING SETUP
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("PhantomBot")

# ==========================================
# INTENTS & BOT INITIALIZATION
# ==========================================
intents = discord.Intents.default()

# Initialized without prefix commands (Slash commands only)
bot = commands.Bot(
    command_prefix=[],
    intents=intents,
    help_command=None
)

# ==========================================
# ROTATING ACTIVITIES SETUP (5 Sec Cycle)
# ==========================================
ACTIVITIES = [
    discord.Game(name="with Railway Deployments"),
    discord.Activity(type=discord.ActivityType.watching, name="over the server"),
    discord.Activity(type=discord.ActivityType.listening, name="for new cogs"),
    discord.Game(name="Python 3.11"),
    discord.Activity(type=discord.ActivityType.competing, name="uptime streak")
]

@tasks.loop(seconds=5)
async def status_cycler():
    """Cycles through 5 status activities every 5 seconds."""
    for activity in ACTIVITIES:
        try:
            await bot.change_presence(activity=activity)
            await asyncio.sleep(5)
        except Exception as e:
            logger.warning(f"Error updating presence: {e}")

@status_cycler.before_loop
async def before_status_cycler():
    """Waits for internal cache readiness prior to task launch."""
    await bot.wait_until_ready()

# ==========================================
# COG AUTOMATION & LOADER
# ==========================================
async def load_all_cogs():
    """Scans cogs/ directory and registers all python files."""
    cogs_dir = "./cogs"
    if not os.path.exists(cogs_dir):
        logger.warning(f"Directory '{cogs_dir}' missing. Creating directory automatically.")
        os.makedirs(cogs_dir)
        return

    for filename in os.listdir(cogs_dir):
        if filename.endswith(".py") and not filename.startswith("__"):
            cog_name = f"cogs.{filename[:-3]}"
            try:
                await bot.load_extension(cog_name)
                logger.info(f"Loaded extension cog: {cog_name}")
            except Exception as e:
                logger.error(f"Failed loading cog extension {cog_name}: {e}")
                traceback.print_exc()

# ==========================================
# SETUP HOOK & SLASH COMMAND AUTO-SYNC
# ==========================================
@bot.event
async def setup_hook():
    """Executes background loading and automatically syncs slash commands from cogs/."""
    logger.info("Starting bot initialization sequence...")
    
    # Step 1: Load all cogs inside cogs/ folder
    await load_all_cogs()
    
    # Step 2: Sync all slash commands defined inside those cogs with Discord API
    logger.info("Syncing slash commands (/) with Discord Gateway...")
    try:
        synced = await bot.tree.sync()
        logger.info(f"Successfully synced {len(synced)} slash command(s) across all cogs!")
    except Exception as e:
        logger.error(f"Failed to auto-sync slash commands during setup_hook: {e}")

# ==========================================
# CONNECTION EVENTS
# ==========================================
@bot.event
async def on_ready():
    """Triggers when gateway connection is fully established."""
    logger.info("==========================================")
    logger.info(f"Logged in as : {bot.user.name}")
    logger.info(f"Bot ID        : {bot.user.id}")
    logger.info(f"Guilds        : {len(bot.guilds)}")
    logger.info("==========================================")

    if not status_cycler.is_running():
        status_cycler.start()
        logger.info("Background status cycler task started.")

@bot.event
async def on_resumed():
    """Triggers when a disconnected session is successfully resumed."""
    logger.info("Bot session successfully resumed.")

@bot.event
async def on_disconnect():
    """Triggers when bot loses connection to Discord."""
    logger.warning("Bot disconnected from Discord Gateway.")

# ==========================================
# BOT EXECUTION (BOT.RUN)
# ==========================================
if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    
    if not token:
        logger.critical("DISCORD_TOKEN environment variable not set! Shutting down.")
        sys.exit(1)
        
    try:
        logger.info("Starting Phantom Bot via bot.run()...")
        bot.run(token)
    except KeyboardInterrupt:
        logger.info("Bot execution terminated manually.")
    except Exception as fatal_error:
        logger.critical(f"Fatal error encountered during execution: {fatal_error}")
  
