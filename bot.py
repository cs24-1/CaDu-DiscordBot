import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import asyncio
from utils import constants


intents = discord.Intents.default()
intents.message_content = True

load_dotenv()



try:
    asyncio.get_running_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

bot = commands.Bot(
    command_prefix=os.getenv('BOT_PREFIX'),
    intents=intents
    )

@bot.event
async def on_ready():
    print(f"✅ Eingeloggt als {bot.user} (ID: {bot.user.id})")
    print("------")

async def load_cogs():
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py'):
            bot.load_extension(f'cogs.{filename[:-3]}')
            print(f"🔄 Geladene Cog: {filename}")

async def main():
    async with bot:
        await load_cogs()
        await bot.start(constants.Secrets.DISCORD_TOKEN)

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())