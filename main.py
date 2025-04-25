import discord
from discord.ext import commands, tasks
import json
import os
import requests
from datetime import datetime
from dotenv import load_dotenv
import warnings
from urllib3.exceptions import InsecureRequestWarning
from requests.exceptions import RequestException

# Lade Umgebungsvariablen
load_dotenv()

token = os.getenv("DISCORD_TOKEN")
prefix = os.getenv("BOT_PREFIX")
owner_id = os.getenv("OWNER_ID")
channel_id = os.getenv("CHANNEL_ID")
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
    # Aufteilen des Textes in kleinere Nachrichten
    await send_long_message(channel, stundenplan)

# Funktion zum Abrufen des Stundenplans
def hole_stundenplan():
    url = f"https://selfservice.campus-dual.de/room/json?userid={campus_user}&hash={campus_hash}"

    # Ignoriere SSL-Zertifikatswarnungen (unsicher, nur temporär)
    warnings.simplefilter("ignore", InsecureRequestWarning)
    
    try:
        # SSL-Verifizierung deaktiviert und Timeout hinzugefügt
        response = requests.get(url, verify=False, timeout=10)  # Timeout von 10 Sekunden
        response.raise_for_status()  # Sicherstellen, dass der Statuscode 200 ist

        # Prüfen, ob die Antwort erfolgreich war
        if response.status_code != 200:
            return f"❌ Fehler beim Abrufen des Stundenplans. Statuscode: {response.status_code}"

        data = response.json()
    except RequestException as e:
        # Erweitert Fehlerbehandlung: alle möglichen Netzwerk-/Verbindungsfehler
        return f"❌ Fehler bei der Anfrage: {str(e)}"
    except ValueError:
        return "❌ Ungültige JSON-Antwort vom Server."
    except Exception as e:
        return f"❌ Unerwarteter Fehler: {e}"

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

# Hilfsfunktion zum Senden langer Nachrichten
async def send_long_message(channel, content):
    # Wenn die Nachricht mehr als 2000 Zeichen hat, teile sie auf
    while len(content) > 2000:
        await channel.send(content[:2000])  # Sende die ersten 2000 Zeichen
        content = content[2000:]  # Kürze den Text um die gesendeten 2000 Zeichen

    # Sende den restlichen Text
    if content:
        await channel.send(content)

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

# Kommando für den Stundenplan
@bot.command()
async def stundenplan(ctx):
    try:
        plan = hole_stundenplan()
        # Aufteilen des Textes in kleinere Nachrichten
        await send_long_message(ctx, plan)
    except requests.exceptions.SSLError:
        await ctx.send("❌ SSL-Fehler: Zertifikat konnte nicht validiert werden. Bitte Setup prüfen.")
    except Exception as e:
        await ctx.send(f"❌ Unerwarteter Fehler: {e}")

# Einfacher Ping-Befehl
@bot.command()
async def ping(ctx):
    await ctx.send("🏓 Pong!")

# Bot starten
bot.run(token)


