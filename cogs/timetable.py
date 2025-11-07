import asyncio
from datetime import datetime
from discord import option
import discord
from discord.ext import commands, tasks  # tasks for @tasks.loop decorator
import os
import pytz
import requests

# Import custom utilities
from utils import timetableUtils, constants

# Load environment variables

GUILD_ID = constants.Secrets.GUILD_ID
QUOTE_CHANNEL_ID = constants.ChannelIDs.QUOTE_CHANNEL_ID

class Timetable(commands.Cog):
    """A Discord cog that provides commands to view the class timetable.
    
    This cog allows users to fetch and display class schedules for different time periods
    using slash commands. It integrates with the Campus Dual system to provide up-to-date
    timetable information.
    """
    
    def __init__(self, bot):
        """Initialize the Timetable cog.
        
        Args:
            bot: The Discord bot instance
        """
        self.bot = bot

    # --- Slash Command ---
    @discord.slash_command(
        name="timetable",
        description="Shows the timetable for today, tomorrow, or the next n days.",
        guild_ids=[GUILD_ID]  # Register only in your guild
    )
    @option(
        "argument",
        description="'today', 'tomorrow', or a number (1-30). Default is 7",
        required=False,
        default="7"
    )
    async def timetable(self, ctx: discord.ApplicationContext, argument: str):
        """Fetch and display the class timetable.

        This command allows users to view the class schedule for different time periods.
        Users can request the schedule for today, tomorrow, or any number of upcoming days.

        Args:
            ctx: The Discord application context
            argument: The time period to fetch:
                     - "?" for help
                     - "today" for today's schedule
                     - "tomorrow" for tomorrow's schedule
                     - a number (1-30) for that many upcoming days
                     - defaults to 7 days if not specified
        """
        await ctx.defer()  # Defer response in case the request takes time

        try:
            # --- Argument logic ---
            if argument == "?":
                plan = (
                    "ℹ️ **Available Commands:**\n\n"
                    "`/timetable today`\n"
                    "→ Shows the timetable for **today**.\n\n"
                    "`/timetable tomorrow`\n"
                    "→ Shows the timetable for **tomorrow**.\n\n"
                    "`/timetable`\n"
                    "→ Shows the timetable for the **next 7 days**.\n\n"
                    "`/timetable <number>`\n"
                    "→ Shows the timetable for the next `<number>` days (max. 30)."
                )
            elif argument.lower() == "today":
                plan = timetableUtils.get_timetable(days=0)
            elif argument.lower() == "tomorrow":
                plan = timetableUtils.get_timetable(days=1)
            elif argument.isdigit():
                days = int(argument)
                if days <= 0 or days > 30:
                    await ctx.respond("❌ Please enter a number between 1 and 30.")
                    return
                plan = timetableUtils.get_timetable(days=days)
            else:
                plan = "❌ Invalid argument. Use 'today', 'tomorrow', or a number (1–30)."

            await self.send_long_message(ctx, plan)

        except requests.exceptions.SSLError:
            await ctx.respond("❌ SSL Error: Certificate could not be validated.")
        except Exception as e:
            await ctx.respond(f"❌ Unexpected error: {e}")

    # --- Automated daily task ---
    @tasks.loop(hours=24)
    async def daily_timetable_task(self):
        """Runs every day at 6 AM Berlin time, skips weekends & holidays."""
        await self.bot.wait_until_ready()
        berlin = pytz.timezone("Europe/Berlin")
        now = datetime.now(tz=berlin)
        target_time = now.replace(hour=6, minute=0, second=0, microsecond=0)

        # Wait until 6 AM local time if task started at bot boot
        if now < target_time:
            wait_seconds = (target_time - now).total_seconds()
            print(f"⏳ Waiting until {target_time.strftime('%Y-%m-%d %H:%M:%S')} ({int(wait_seconds)}s)")
            await asyncio.sleep(wait_seconds)

        # --- After wake-up: perform the daily action ---
        today = datetime.now(tz=berlin).date()
        channel = self.bot.get_channel(QUOTE_CHANNEL_ID)

        if not channel:
            print("❌ Channel not found.")
            return

        # Skip weekends
        if today.weekday() >= 5:
            print("⏭ Weekend — skipping timetable post.")
            return

        # Skip holidays
        if today in constants.TimeConstants.HOLIDAYS:
            print("⏭ Holiday — skipping timetable post.")
            return

        print(f"📨 Sending timetable for {today.isoformat()}...")
        timetable_text = timetableUtils.get_timetable(days=0)
        await self.send_long_message(channel, timetable_text)

    @daily_timetable_task.before_loop
    async def before_daily_timetable_task(self):
        """Ensure bot is ready before the loop starts."""
        await self.bot.wait_until_ready()
        print("🕕 Daily timetable task initialized.")

    async def send_long_message(self, target, text: str):
        """Split messages into 2000-character chunks."""
        chunks = [text[i:i + 2000] for i in range(0, len(text), 2000)]
        for chunk in chunks:
            if isinstance(target, discord.ApplicationContext):
                await target.respond(chunk)
            else:
                await target.send(chunk)

    # --- Helper function for long messages ---
    async def send_long_message(self, ctx, text: str):
        """Split messages into 2000-character chunks (Discord limit).
        
        Args:
            ctx: The Discord context to respond to
            text: The text message to split and send
        """
        chunks = [text[i:i+2000] for i in range(0, len(text), 2000)]
        for chunk in chunks:
            await ctx.respond(chunk)

    @commands.Cog.listener()
    async def on_ready(self):
        print("📦 Cog 'Timetable' ready.")


def setup(bot):
    bot.add_cog(Timetable(bot))
