import discord
from discord.ext import commands, tasks
import json
import os
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(dotenv_path=r"H:\Visual Studio Code\CaDu-DiscordBot\.env")

token = os.getenv("DISCORD_TOKEN")
prefix = os.getenv("BOT_PREFIX")
owner_id_raw = os.getenv("OWNER_ID")
owner_id = int(owner_id_raw)
channel_id = int(os.getenv("CHANNEL_ID"))
campus_hash = os.getenv("CAMPUS_HASH")
campus_user = os.getenv("CAMPUS_USER")

# Intents (nur das Nötigste, kannst du bei Bedarf erweitern)
intents = discord.Intents.default()
intents.message_content = True 

# Bot-Instanz
bot = commands.Bot(command_prefix=prefix, intents=intents, owner_id=owner_id)


# Hintergrundaufgabe: Stundenplan alle 24h posten
@tasks.loop(hours=24)
async def stundenplan_task():
    channel = bot.get_channel(channel_id)
    if channel is None:
        print("❌ Kanal nicht gefunden.")
        return
    stundenplan = hole_stundenplan()
    await channel.send(stundenplan)


# Funktion zum Abrufen des Stundenplans
def hole_stundenplan():
    url = f"https://selfservice.campus-dual.de/room/json?userid={campus_user}&hash={campus_hash}"
    response = requests.get(url)
    if response.status_code != 200:
        return "❌ Fehler beim Abrufen des Stundenplans."

    try:
        data = response.json()
    except ValueError:
        return "❌ Ungültige JSON-Antwort vom Server."

    eintraege = data if isinstance(data, list) else data.get("entries", [])

    if not eintraege:
        return "ℹ️ Kein Stundenplan gefunden."

    output = "📅 **Stundenplan**\n\n"
    for eintrag in eintraege:
        start_dt = datetime.fromtimestamp(eintrag["start"])
        end_dt = datetime.fromtimestamp(eintrag["end"])
        datum = start_dt.strftime("%A, %d.%m.%Y")
        start = start_dt.strftime("%H:%M")
        end = end_dt.strftime("%H:%M")

        output += f"📌 **{datum}**\n"
        output += f"🕒 {start}–{end} | **{eintrag['title']}**\n"
        output += f"📚 {eintrag['description']}\n"
        output += f"🏫 Raum: {eintrag['room']}\n"
        if eintrag.get("remarks"):
            output += f"📝 Hinweis: {eintrag['remarks']}\n"
        output += "\n"

    return output.strip()


# Wenn der Bot bereit ist
@bot.event
async def on_ready():
    print(f"✅ Eingeloggt als {bot.user}")
    print(f"📦 Discord.py Version: {discord.__version__}")
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching, name=f"{bot.command_prefix}help"
        )
    )
    stundenplan_task.start()


@bot.command()
async def stundenplan(ctx):
    plan = hole_stundenplan()
    await ctx.send(plan)


@bot.command()
async def ping(ctx):
    await ctx.send("🏓 Pong!")


# Bot starten
bot.run(token)
