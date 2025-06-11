import os
import asyncio
import warnings
import random

import json
import requests
from urllib3.exceptions import InsecureRequestWarning
from requests.exceptions import RequestException

import pytz
from datetime import datetime, timezone, timedelta, date

import discord
from discord.ext import commands
from dotenv import load_dotenv

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


# Ping-Zähler initialisieren
ping_counter = {}  

# Lade bestehende Daten (falls vorhanden)
def load_ping_counter():
    global ping_counter
    try:
        with open("ping_counter.json", "r") as f:
            ping_counter: dict = json.load(f)
            ping_counter: dict = {int(k): v for k, v in ping_counter.items()}  # Keys in int konvertieren
    except FileNotFoundError:
        ping_counter = {}

# Speichere aktuelle Zählerstände
def save_ping_counter():
    with open("ping_counter.json", "w") as f:
        json.dump(ping_counter, f)

pingpong_counter = {}

def load_pingpong_counter():
    global pingpong_counter
    try:
        with open("pingpong_win_counter.json", "r") as f:
            # Sicherstellen, dass die Datei korrekt formatiert ist
            data = json.load(f)
            # Initialisiere Ping und Pong wenn nicht vorhanden
            pingpong_counter["Ping"] = data.get("Ping", 0)
            pingpong_counter["Pong"] = data.get("Pong", 0)
    except (FileNotFoundError, json.JSONDecodeError):
        # Fallback auf Standardwerte
        pingpong_counter = {"Ping": 0, "Pong": 0}
        print("Fehler beim Laden des PingPong Zählers, Standardwerte werden verwendet.")

def save_pingpong_counter():
    with open("pingpong_win_counter.json", "w") as f:
        # Stellen Sie sicher, dass der Counter korrekt gespeichert wird
        json.dump(pingpong_counter, f, indent=4)

def update_pingpong_winner(winner: str):
    if winner == "Ping":
        pingpong_counter["Ping"] += 1
    elif winner == "Pong":
        pingpong_counter["Pong"] += 1
    save_pingpong_counter()


# Liste mit Feiertagen

FEIERTAGE = {
    date(2025, 1, 1),    # Neujahr
    date(2025, 4, 18),   # Karfreitag
    date(2025, 4, 21),   # Ostermontag
    date(2025, 5, 1),    # Tag der Arbeit
    date(2025, 5, 29),   # Christi Himmelfahrt
    date(2025, 6, 9),    # Pfingstmontag
    date(2025, 10, 3),   # Tag der Deutschen Einheit
    date(2025, 12, 25),  # 1. Weihnachtstag
    date(2025, 12, 26),  # 2. Weihnachtstag
}

# Statt @tasks.loop(hours=24)
async def stundenplan_task():
    await bot.wait_until_ready()
    berlin = pytz.timezone("Europe/Berlin")
    
    while not bot.is_closed():
        now = datetime.now(tz=berlin)
        target_time = now.replace(hour=6, minute=0, second=0, microsecond=0)

        # Wenn 6 Uhr heute schon vorbei ist, nimm 6 Uhr morgen
        if now >= target_time:
            target_time += timedelta(days=1)

        wait_seconds = (target_time - now).total_seconds()
        print(f"⏳ Warte bis {target_time.strftime('%Y-%m-%d %H:%M:%S')} ({int(wait_seconds)} Sekunden)")
        await asyncio.sleep(wait_seconds)

        # Jetzt ist es 6 Uhr in Berlin
        channel = bot.get_channel(int(channel_id))
        if channel is None:
            print("❌ Kanal nicht gefunden.")
            continue

        today = datetime.now(tz=berlin).date()

        if today.weekday() >= 5:
            print("⏭ Wochenende ~ Stundenplan wird nicht gesendet.")
            continue

        if today in FEIERTAGE:
            print("⏭ Feiertag ~ Stundenplan wird nicht gesendet.")
            continue

        stundenplan = hole_stundenplan(0)
        await send_long_message(channel, stundenplan)

# Funktion zum Abrufen des Stundenplans
def hole_stundenplan(tage):
    url = f"https://selfservice.campus-dual.de/room/json?userid={campus_user}&hash={campus_hash}"

    # Ignoriere SSL-Zertifikatswarnungen (unsicher, nur temporär)
    warnings.simplefilter("ignore", InsecureRequestWarning)
    
    try:
        # SSL-Verifizierung deaktiviert und Timeout hinzugefügt
        response = requests.get(url, verify=False)  # Timeout von 10 Sekunden
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

    # Zeitzone Berlin
    berlin = pytz.timezone("Europe/Berlin")
    now = datetime.now(tz=berlin)
    heute0 = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # 1) Zeitfenster festlegen
    if tage == 0:
        start_date   = heute0
        zeitraum_end = heute0 + timedelta(days=1)
    elif tage == 1:
        start_date   = heute0 + timedelta(days=1)
        zeitraum_end = start_date + timedelta(days=1)
    else:
        start_date   = heute0
        zeitraum_end = heute0 + timedelta(days=tage)

    # 2) Filtern (Timestamp → UTC → Berlin)
    gefilterte_eintraege = []
    for e in eintraege:
        start_dt = datetime.fromtimestamp(e["start"], tz=timezone.utc).astimezone(berlin)
        if start_date <= start_dt < zeitraum_end:
            gefilterte_eintraege.append(e)

    if not gefilterte_eintraege:
        if tage == 0:
            return "ℹ️ Kein Stundenplan für heute gefunden."
        elif tage == 1:
            return "ℹ️ Kein Stundenplan für morgen gefunden."
        return f"ℹ️ Kein Stundenplan für die nächsten {tage} Tage gefunden."

    output = f"📅 **Stundenplan für {'heute' if tage == 0 else 'morgen' if tage == 1 else 'die nächsten ' + str(tage) + ' Tage'}**\n\n"
    
    # Gruppiere nach Datum
    tage_gruppiert = {}
    for eintrag in gefilterte_eintraege:
        start_dt = datetime.fromtimestamp(eintrag["start"])
        datum = start_dt.strftime("%A, %d.%m.%Y")  # Datum im Format "Montag, 29.04.2025"
        
        if datum not in tage_gruppiert:
            tage_gruppiert[datum] = []
        
        tage_gruppiert[datum].append(eintrag)

    # Jetzt wird der Stundenplan nach Tagen und nebeneinander angezeigt
    for datum, eintraege in tage_gruppiert.items():
        output += f"📌 **{datum}**:\n"
        for i, eintrag in enumerate(eintraege):
            berlin = pytz.timezone("Europe/Berlin")
            start_dt = datetime.fromtimestamp(eintrag["start"], tz=timezone.utc).astimezone(berlin)
            end_dt = datetime.fromtimestamp(eintrag["end"], tz=timezone.utc).astimezone(berlin)
            start = start_dt.strftime("%H:%M")  # Uhrzeit im Format 24h
            end = end_dt.strftime("%H:%M")  # Uhrzeit im Format 24h
            title = eintrag["title"]

            # Formatierung der Anzeige nebeneinander
            if i % 2 == 0:  # Erste Spalte
                output += f"📚 {eintrag['description']}\n"
                output += f"🕒 {start}–{end}\n"
                output += f"🏫 Raum: {eintrag['room']}\n"
                output += f"\n"
            else:  # Zweite Spalte
                output += f"📚 {eintrag['description']}\n"
                output += f"🕒 {start}–{end}\n"
                output += f"🏫 Raum: {eintrag['room']}\n"
                output += f"\n"
        
        output += "\n"

    return output.strip()

async def send_long_message(channel, content):
    # Wenn die Nachricht mehr als 2000 Zeichen hat, teile sie auf
    while len(content) > 2000:
        await channel.send(content[:2000])  # Sende die ersten 2000 Zeichen
        content = content[2000:]  # Kürze den Text um die gesendeten 2000 Zeichen

    # Sende den restlichen Text, falls noch was übrig ist
    if content:
        await channel.send(content)


# Wenn der Bot bereit ist
@bot.event
async def on_ready():
    load_ping_counter()
    load_pingpong_counter()
    print(f"✅ Eingeloggt als {bot.user}")
    print(f"📦 Discord.py Version: {discord.__version__}")
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching, name=f"{bot.command_prefix}help"
        )
    )
    bot.loop.create_task(stundenplan_task())

# Kommando für den Stundenplan
@bot.command()
async def stundenplan(ctx, argument: str = "7"):
    """
    Holt den Stundenplan für heute, morgen oder die nächsten 'tage' Tage. Standard sind 7 Tage.
    """
    try:
        if argument == "?":
            plan = """
            ℹ️ 📚 Verfügbare Befehle:
            
            !stundenplan heute
            Zeigt den Stundenplan für den heutigen Tag an.
            
            !stundenplan morgen
            Zeigt den Stundenplan für morgen an.
            
            !stundenplan 
            Zeigt den Stundenplan für die nächsten 7 Tage an.

            !stundenplan {int}
            Zeigt den Stundenplan für die nächsten {int} Tage an. Ersetze {int} durch die Anzahl der gewünschten Tage (z. B. !stundenplan 3 für die nächsten 3 Tage, max. 30).
            """
        elif argument == "heute":  # Wenn "heute" angegeben wird, den Plan für heute abrufen
            plan = hole_stundenplan(tage=0)
        elif argument == "morgen":  # Wenn "morgen" angegeben wird, den Plan für morgen abrufen
            plan = hole_stundenplan(tage=1)
        elif argument.isdigit():  # Wenn eine Zahl angegeben wird, die Anzahl der Tage verwenden
            if int(argument) <= 0 or int(argument) > 30:
                await ctx.send("❌ Bitte gib eine Tagesanzahl zwischen 1 und 30 an.")
                return
            plan = hole_stundenplan(tage=int(argument))
        else:
            plan = "❌ Ungültiges Argument. Bitte benutze 'heute', 'morgen' oder eine Zahl für die nächsten Tage."

        await send_long_message(ctx, plan)

    except requests.exceptions.SSLError:
        await ctx.send("❌ SSL-Fehler: Zertifikat konnte nicht validiert werden. Bitte Setup prüfen.")
    except Exception as e:
        await ctx.send(f"❌ Unerwarteter Fehler: {e}")

# Einfacher Ping-Befehl
@bot.command()
async def ping(ctx, argument: str = None):
    user_id = ctx.author.id
    user_name = ctx.author.display_name

    if argument == "count":
        count = ping_counter.get(user_id, 0)
        await ctx.send(f"🏓 Du hast den Ping-Befehl {count} Mal benutzt.")

    elif argument == "scoreboard":
        if not ping_counter:
            await ctx.send("📉 Noch keine Ping-Daten vorhanden.")
            return

        # Top 10 sortieren
        sorted_users = sorted(ping_counter.items(), key=lambda x: x[1], reverse=True)[:10]

        output = "**🏓 Ping-Scoreboard**\n\n"
        for i, (uid, count) in enumerate(sorted_users, 1):
            try:
                user = await bot.fetch_user(uid)
                output += f"**{i}.** {user.name}#{user.discriminator}: `{count}` Pings\n"
            except:
                output += f"**{i}.** Unbekannter Nutzer ({uid}): `{count}` Pings\n"

        await ctx.send(output)

    else:
        # Zähler erhöhen
        ping_counter[user_id] = ping_counter.get(user_id, 0) + 1
        save_ping_counter()
        count = ping_counter[user_id]

        if count == 5:
            await ctx.send(f"🏓 Pong! {user_name}, du hast diesen Befehl bereits {count} Mal benutzt. Hast du nichts besseres zu tun?")
        elif count == 10:
            await ctx.send(f"""🏓 Pong! {user_name}, du hast diesen Befehl bereits {count} Mal benutzt.
 
                                ⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡿⠿⠛⠛⠛⠛⠿⣿⣿⣿⣿⣿⣿⣿⣿
                                ⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡿⠛⠉⠁⠀⠀⠀⠀⠀⠀⠀⠉⠻⣿⣿⣿⣿⣿⣿
                                ⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡟⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠘⢿⣿⣿⣿⣿
                                ⣿⣿⣿⣿⣿⣿⣿⣿⣿⡟⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣾⣿⣿⣿⣿
                                ⣿⣿⣿⣿⣿⣿⣿⠋⠈⠀⠀⠀⠀⠐⠺⣖⢄⠀⠀⠀⠀⠀⠀⠀⠀⣿⣿⣿⣿⣿
                                ⣿⣿⣿⣿⣿⣿⡏⢀⡆⠀⠀⠀⢋⣭⣽⡚⢮⣲⠆⠀⠀⠀⠀⠀⠀⢹⣿⣿⣿⣿
                                ⣿⣿⣿⣿⣿⣿⡇⡼⠀⠀⠀⠀⠈⠻⣅⣨⠇⠈⠀⠰⣀⣀⣀⡀⠀⢸⣿⣿⣿⣿
                                ⣿⣿⣿⣿⣿⣿⡇⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣟⢷⣶⠶⣃⢀⣿⣿⣿⣿⣿
                                ⣿⣿⣿⣿⣿⣿⡅⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢿⠀⠈⠓⠚⢸⣿⣿⣿⣿⣿
                                ⣿⣿⣿⣿⣿⣿⡇⠀⠀⠀⠀⢀⡠⠀⡄⣀⠀⠀⠀⢻⠀⠀⠀⣠⣿⣿⣿⣿⣿⣿
                                ⣿⣿⣿⣿⣿⣿⡇⠀⠀⠀⠐⠉⠀⠀⠙⠉⠀⠠⡶⣸⠁⠀⣠⣿⣿⣿⣿⣿⣿⣿
                                ⣿⣿⣿⣿⣿⣿⣿⣦⡆⠀⠐⠒⠢⢤⣀⡰⠁⠇⠈⠘⢶⣿⣿⣿⣿⣿⣿⣿⣿⣿
                                ⣿⣿⣿⣿⣿⣿⣿⣿⡇⠀⠀⠀⠀⠠⣄⣉⣙⡉⠓⢀⣾⣿⣿⣿⣿⣿⣿⣿⣿⣿
                                ⣿⣿⣿⣿⣿⣿⣿⣿⣷⣄⠀⠀⠀⠀⠀⠀⠀⠀⣰⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿
                                ⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣷⣤⣀⣀⠀⣀⣠⣾⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿""")
        elif count == 300:
            await ctx.send(f"""🏓 Pong! {user_name}, du hast diesen Befehl bereits {count} Mal benutzt. That's kinda sus!
 
                                ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣀⣤⣶⣶⣶⣶⣶⣤⣀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣴⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣷⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣴⣿⣿⣿⣿⢿⣻⣿⣶⣼⣿⣿⣿⡿⠿⣦⣤⣀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣼⣿⣿⣿⣿⢯⣿⣿⠟⣻⢭⡛⠁⡀⠠⠐⠀⠉⠻⣿⣦⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣠⣤⣾⣿⣿⣿⣿⣻⣿⣿⢏⡚⢥⢊⠇⠀⠄⡁⠄⠀⢀⠀⡀⢹⣿⡄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣶⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠠⡝⣢⠏⣶⡌⠀⠄⠂⢁⠂⠐⢠⣼⣿⠇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢠⣿⣿⣿⣿⣿⣿⣿⣿⣿⢿⣽⣿⣿⡄⠠⠁⢊⡽⠿⢶⣶⣥⡶⢶⣻⣿⣿⠏⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠐⠀⠀⠀⠀⠀⠀⢀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣀⣤⣤⣾⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣯⣿⣿⣷⣤⣌⣀⢌⣍⣒⣲⣃⣮⣵⣿⡟⠁⠀⢀⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠠⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣀⣀⣤⣤⣴⣤⣶⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣷⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣷⣦⣄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣀⣠⣤⣤⣶⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣟⣿⣿⣿⣻⣿⣿⣿⣿⣿⢿⣳⡿⣿⢿⣿⡿⣿⢿⣟⡿⣽⣻⣿⣿⢯⣟⡿⣽⣿⡋⢻⡿⣿⢿⣿⣦⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣀⣴⣾⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣾⣿⣿⣿⣿⣿⣿⣿⣯⣿⣽⣻⡾⣽⣟⡿⣾⣻⢯⣿⣿⣿⣿⢯⣟⡿⣞⣿⢿⣽⢯⣿⣿⣿⣿⣦⣤⣄⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣠⣾⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⢿⣻⢿⡽⣯⣟⣿⣻⣽⣿⣿⣿⣿⣿⣾⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣷⣿⣽⣟⡾⣟⣷⣿⣻⢿⡿⣿⣿⡿⣯⣟⡿⣽⣿⣾⣿⣿⣿⣿⣿⣿⣿⣿⣿⣷⣦⣄⠀⠀⠀⠀⠀⠀⠀⡠⡀⠀⠀⠀⠀⠑⠀⠀⠀⠤⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣾⣿⣿⣿⣿⣿⣿⣿⣿⠟⢋⣽⢾⣟⣯⣿⣻⣷⣿⣾⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⢿⣿⣿⣿⣿⣿⣿⣿⣿⣯⣿⣿⣿⣯⣿⣿⣿⣷⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣷⣻⣞⡷⣯⣧⡼⣿⣿⣦⡄⠀⠀⠀⠀⢄⠀⠀⠐⠀⠀⠀⠀⠀⠀⠀⠀⠀⠄⠁⠁⡀⠐⠂⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣾⣿⣿⣿⣿⣿⣿⢿⣽⡾⣶⡿⣾⣻⣾⣿⣿⣿⡿⣿⣻⣽⣿⣿⡿⣟⡿⣯⣟⡷⣏⣠⣿⣻⣾⣷⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⢿⡿⣿⣿⣿⣿⣿⣿⣽⣻⣽⣻⡽⣟⡟⠛⣿⣿⣟⣷⣯⢿⣳⣟⡿⣿⣦⡀⠀⠀⠀⠀⠀⠀⠂⠀⠀⠀⠀⠈⠀⠀⠀⢀⠀⠄⠀⠈⠂⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣼⣿⣿⣿⣿⣿⡿⣯⢿⡾⣽⣷⣿⣿⣿⢿⣻⣽⡾⣽⡷⣟⣿⢯⣷⢿⣻⣽⣷⣻⣟⣿⣿⣿⡿⣟⡿⣽⢯⡿⣽⣻⣿⣿⣿⣿⣿⣟⣾⢯⣿⣳⣯⣟⣿⣻⢿⣿⣿⣿⣷⣿⣻⣟⡿⣽⣻⣿⣿⣾⣟⡿⣞⣿⡽⣿⣷⡄⠀⠀⠀⠀⠆⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠂⡤⠇⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢰⣿⣿⣿⣿⣿⡿⣽⣻⣯⢿⡿⣟⣿⡽⣾⣻⣽⣾⣻⣽⣻⣽⡾⣿⣽⣻⣽⣾⣷⣿⡿⣟⡿⣾⡽⣿⡽⣟⣯⣿⣻⣷⡈⢻⣿⣿⣿⣿⣞⣿⣳⣯⡷⣿⢾⣽⣻⣿⠿⢿⣿⣿⣿⣿⣽⣟⣷⢯⣟⡿⣞⣿⢯⣷⢿⣯⣿⣿⡀⠀⠀⠐⠄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠁⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣠⣾⣿⣿⣿⣿⣿⣽⣻⢷⣻⣯⣟⡿⣞⣿⣽⣻⣞⣷⣯⡷⣟⣷⢿⣳⣯⣟⡾⣷⢯⣷⢿⣻⣽⡷⣿⣳⣿⣻⣽⡾⣽⣻⣿⣿⣿⣿⣿⣷⡿⣾⣽⣳⡿⣯⢿⣞⡿⣿⣶⣤⣾⡿⣯⣟⡿⣿⣿⣿⣽⣻⣟⣾⣿⣯⣿⣞⡷⣿⣧⣄⠀⠀⠘⠆⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⣀⣴⣾⣿⣿⣿⣿⣿⣿⣟⣾⡽⣟⡿⣾⣽⣻⢯⣷⣯⣷⣿⣿⣾⡽⣟⣾⣟⡿⣾⣽⣻⣽⢿⣾⣻⡽⣷⣻⢷⣟⡷⣯⣷⣟⣿⣳⣟⣾⣽⣿⣿⣿⣽⢷⣯⡷⣿⣻⢯⣿⡽⣯⣟⡿⣽⣻⢷⣻⣽⢯⣟⣿⣿⣷⣿⣿⣿⣿⣷⣻⣽⣿⣿⣿⣿⣶⣄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⣸⣿⣿⣿⣿⣿⣿⣿⣿⣿⣟⡾⣟⣯⣿⣷⣯⣿⣿⣿⣿⣿⣿⣿⣿⣿⣯⣷⡿⣽⡷⣯⣟⣾⣟⣾⡽⣿⡽⣯⣿⢾⣻⣽⡾⣽⣾⣻⢾⣽⣻⣿⣿⣿⢯⣿⢾⣽⡷⣟⣯⣷⢿⣻⢾⡿⣽⣯⢿⣯⣟⣯⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣾⣿⣿⣿⣿⣿⣷⣄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⣿⣿⣿⣿⣿⣿⣿⣿⣽⣿⣿⣿⣿⡿⣿⢿⣿⣿⡿⣿⣿⣿⣿⣿⣟⣿⣿⣿⣿⣿⣿⣷⣿⣳⣯⣿⡽⣷⣟⡿⣞⣿⣽⣳⣿⣻⢾⣽⣻⡽⣿⣿⣿⣿⢿⣽⣻⣾⡽⣿⡽⣾⣻⢯⣿⡽⣷⣻⣟⣾⣽⣿⣿⣿⣿⣿⣿⣿⣿⢿⣿⣿⣿⣿⣿⣷⡿⣿⣿⣿⣿⣦⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⢸⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡿⣯⡷⣟⣯⡿⠋⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⢿⣻⣞⡿⣯⣷⣻⣽⣞⣯⡿⣽⢯⣟⣿⣿⣿⣿⣟⣾⢷⣯⢿⣳⡿⣯⣟⣯⣷⢿⣯⣷⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣯⣿⣞⡿⣿⣿⣿⣿⣿⢯⣿⣿⣟⣿⡆⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⣸⣿⣿⣿⣿⣿⣯⣟⡿⣿⣽⣻⢷⣟⣿⡿⢁⣼⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⢿⣿⣿⣷⣿⣾⣿⣽⣯⣟⣷⣯⣟⣾⣽⣳⣿⣯⣿⣿⣿⣿⣿⣿⣿⣾⣻⢾⣟⣯⢿⣳⡿⣽⣾⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣷⡿⣽⣇⡙⢿⣿⣽⣻⢷⣿⣿⣿⣿⣄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⢀⣿⣿⣿⣿⣿⡿⣾⣽⣻⢷⣯⣟⣿⣾⣏⣴⣿⡿⣿⣿⣿⣿⣯⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣟⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣟⣿⣿⣶⣿⢿⣽⣻⣞⣿⣿⡿⣿⣷⣦⣄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⣠⣿⣿⣿⣿⣿⣿⣿⣿⣾⣟⡿⣾⣽⣞⡿⣿⣟⣯⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣾⣿⣿⣯⣿⣯⣿⣿⣻⣽⣿⣿⣿⣿⣿⣟⣿⣿⣿⣿⣿⣿⣿⣿⣻⣿⣿⣿⣿⣿⣿⣿⡿⣿⣻⣽⣿⣿⣿⣿⣿⣿⣷⣿⣿⣿⣿⣷⣿⣾⣯⡷⣿⡽⣾⡽⣿⣳⣟⡿⣿⣧⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⢀⣾⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣻⢷⣻⣾⣻⢷⣿⣿⣿⣿⣿⣿⣷⣿⣟⡿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⢿⡿⣿⣿⣿⣟⡿⣿⢿⣿⣿⣿⣿⣿⣟⡿⣽⣻⣾⣽⣷⣿⣟⣿⣿⣿⣿⡿⢿⣿⣿⣽⣿⣿⣿⣿⣿⣿⣿⣷⣿⣿⣽⣿⣿⣽⣻⣽⣿⣿⣶⣄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⢾⣿⣿⣿⣿⣿⣿⣟⣿⠃⢹⣿⣿⣯⢿⣻⣾⣽⣿⡿⠋⠹⣿⣿⣿⣿⣽⣿⡿⣽⣿⣿⣿⣿⣿⣿⣿⣿⣾⣿⣿⣿⣿⣟⣿⣿⣿⣿⣿⣽⣾⣯⣷⣯⣷⣿⣿⣿⣿⣯⢿⡽⣟⣾⡽⣥⣽⣿⣿⣿⣻⣿⣿⣿⣽⣻⣽⣿⣿⣿⡟⠀⠀⠉⠻⢿⣿⣿⣿⣯⣿⣿⣿⣿⣿⣿⣟⣾⣿⣿⣻⣏⠛⢿⣿⣿⣷⣄⠀⠀⠀⠀⠀⠀⠀⠀
⠀⢻⣿⣿⣿⣿⣿⡿⣞⣿⣷⢾⣿⣿⣯⣿⣿⠿⠛⠁⠀⠀⠀⠹⣿⣿⣿⣽⣿⣿⣟⣾⣽⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⢿⣿⣾⣽⣿⣿⣿⣿⣿⣿⣷⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣟⣿⣿⣯⣿⣿⣿⣿⠟⠀⠀⠀⠀⠀⠀⠈⠉⠙⠛⢿⣿⣿⣿⣿⣿⢯⣿⣿⣿⣻⢿⣶⣀⣿⣿⣿⣿⣦⠀⠀⠀⠀⠀⠀⠀
⠀⣾⣿⣿⣿⣿⣿⣿⢯⡿⣽⡶⣿⣿⣿⠋⠁⠀⠀⠀⠀⠀⠀⠀⠙⢿⣿⣿⣾⣿⣿⣾⣿⣿⣿⣿⣿⣽⣿⣯⢿⣿⣿⣿⣿⣿⣿⣯⡿⣿⢿⡿⣿⣟⡿⢻⣿⣿⣿⡿⣿⢿⣿⣿⣿⣿⡿⣿⣿⣿⣿⣳⣿⣻⣿⣿⣿⣿⡿⠋⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⣿⣿⣿⣯⢿⣿⣿⣿⣟⣯⣿⡟⢻⣿⣷⣻⣿⡆⠀⠀⠀⠀⠀⠀
⢰⣿⣿⣿⣿⣿⣿⣿⣿⣽⢯⣟⣷⢿⣿⡄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠛⢿⣿⣿⣿⣿⣿⣿⣿⢿⣿⣿⣿⣿⣻⢾⣿⣿⣿⣿⣿⣿⣿⣿⣯⣟⣷⣯⣿⣿⣽⣿⣿⣻⣽⣟⣾⣳⣿⣾⣜⣿⣿⣿⣟⡷⣯⣿⣿⣿⠟⠉⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣿⣿⣿⢯⣿⣿⣿⣿⣿⣟⡾⣟⣯⣟⣷⣿⣿⣧⠀⠀⠀⠀⠀⠀
⣼⣿⣿⣿⣿⣿⣿⣿⣿⣿⣯⡿⣾⣻⢿⣿⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠉⠹⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣽⣯⢿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⢯⣟⣷⣿⣿⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣿⣿⣿⣯⡷⣿⣿⣿⣿⣿⡿⣽⣻⢾⣳⣿⣿⣿⠀⠀⠀⠀⠀⠀
⣿⣿⣿⣿⣞⡿⣿⣿⣿⣿⣿⣿⢷⣻⢿⣿⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢹⣿⣿⣿⣿⣿⣿⣿⣿⣿⡷⣯⣿⣻⣿⣿⣿⣿⣿⣿⣿⢿⡿⣟⣟⠻⣿⣿⣿⣟⣿⣻⢿⡿⠿⣟⣿⣿⣿⢯⣟⡿⣞⣿⣿⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣿⣿⣿⣷⣻⢟⣿⣿⣿⣿⣿⣿⣽⣻⣟⣾⣿⣿⠀⠀⠀⠀⠀⠀
⢿⣿⣿⣿⣯⣟⣯⣟⡿⣿⣿⣿⣿⢯⣿⣿⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢻⣿⣿⣯⣿⣿⣿⣿⣿⣿⣟⡾⣷⣻⣿⣿⣿⣿⣿⣿⢿⣿⣿⣿⣿⣿⣿⣿⣾⣷⣿⣯⣿⣷⣿⣿⣿⢯⣟⣯⢿⣻⣿⣿⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢿⣿⣿⣿⣽⢯⣟⣿⣿⣿⣿⣿⣾⣟⡾⣷⣿⣯⠀⠀⠀⠀⠀⠀
⠘⣿⣿⣿⣷⣿⣿⣞⣿⣳⢿⣿⣿⣿⣿⡟⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠘⣿⣿⣿⣽⣿⣿⣿⣿⣿⣿⡽⣷⣟⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣯⣟⣯⣟⣿⣽⣿⣿⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠘⢿⣿⣿⣿⣿⣿⣾⣽⢿⣿⣿⣿⣾⢿⣽⣿⣿⠀⠀⠀⠀⠀⠀
⠀⠙⢿⣿⣿⣿⣿⣿⣞⣯⡿⣞⣿⣿⡟⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢿⣿⣿⡿⣿⣿⣿⣿⣿⣿⣟⣷⣻⣾⣿⣿⣿⣿⣽⣟⣾⣽⣦⣽⣿⣿⣿⣟⣿⣻⢿⣋⣻⣿⣿⡷⣯⢓⣿⣾⣿⣿⡏⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠻⢿⣿⣿⣿⣿⣻⣿⣿⣿⣿⣿⣯⢿⣿⣿⠀⠀⠀⠀⠀⠀
⠀⠀⠈⠻⣿⣿⣿⣿⣿⢾⣽⣿⠻⣿⣿⣦⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠘⣿⣿⣿⡿⣿⣿⣿⣿⣿⣿⣞⡿⣞⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣾⣷⣿⣯⣿⣿⣿⣿⡽⣷⣾⣿⣿⣿⣿⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠉⠛⠿⣿⣿⣿⣿⣿⣿⣿⣿⣻⢿⣿⡇⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠈⠻⢿⣿⣿⣿⣳⣿⣆⠙⣿⣿⣿⣶⣦⣤⣤⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠹⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣽⢿⣽⣿⣿⣿⣿⡿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣳⡿⣽⣾⣿⣿⣿⡟⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠙⢿⣿⣿⣿⣿⣿⣯⢿⣻⣷⡀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⢻⣿⣿⣷⣻⢿⣷⣿⣳⣯⢿⣻⢿⣿⣿⣦⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢹⣿⣿⣷⣿⣿⣿⣿⡿⣿⣿⣿⣾⣿⣿⣿⣿⣻⣿⣾⣷⣻⣾⣷⣻⢶⣻⣞⣷⣿⣿⣿⣟⣿⣿⣿⣿⣿⣿⣷⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⣿⣿⣿⣿⣿⣯⡟⢻⣿⣷⡀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⢸⣿⣿⣿⣽⣻⣽⢾⣯⣟⡿⣽⣿⣿⣿⣿⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣼⣿⣿⣿⣿⣿⣿⣿⣻⣿⣯⣿⣿⢿⣿⣿⣿⣿⣽⣿⣿⣿⣿⡿⣽⣻⣿⣿⣿⣿⣿⢿⣾⣿⣿⣿⣿⣟⡿⣿⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣴⣿⣿⣿⣿⢿⡽⣷⣌⣿⣿⣷⣄⠀⠀
⠀⠀⠀⠀⠀⠀⠀⣾⣿⣿⣿⣳⡿⣽⣻⡾⣽⣻⣿⣈⣿⣿⣿⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢠⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⢿⣯⢿⣾⣿⣿⣟⡷⣯⣿⣿⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣼⣿⣿⣿⣿⣿⢯⣿⣳⣟⡿⣿⣿⣿⣦⠀
⠀⠀⠀⠀⠀⠀⠀⢻⣿⣿⣿⣷⣟⣯⣷⣿⣯⣿⣿⣿⣿⣿⣿⣷⡄⠀⠀⠀⠀⠀⠀⠀⠀⢸⣿⣿⣿⣷⣿⣿⣻⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣷⡿⣿⣿⣿⣿⣽⣿⣿⣿⡿⣯⡿⣾⣻⣿⣿⣟⡾⣟⣷⣿⣿⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠰⣿⣿⣿⣿⣿⣿⣿⣳⣿⣿⣿⣽⣻⣟⣿⡇
⠀⠀⠀⠀⠀⠀⠀⠘⢿⣿⣿⣿⣾⣿⣾⣿⣿⣿⣿⣿⣿⣿⣿⣿⣇⠀⠀⠀⠀⠀⠀⠀⠀⠈⣿⣿⣿⣯⣷⣿⣿⣿⣿⢯⣟⣾⣟⣿⣿⣿⣿⣿⣿⡿⣿⣿⣯⣿⣿⡿⣯⣟⣷⢿⣽⣿⣿⣿⡽⣏⣿⢾⣿⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢹⣿⣿⣿⣿⣟⣷⣿⣿⣿⣷⣿⣷⣿⣿⡇
⠀⠀⠀⠀⠀⠀⠀⠀⠈⠻⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠟⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⢹⣿⣿⣿⣻⣿⢿⣿⣿⣯⡿⣾⣽⢾⡻⣿⣿⣿⣿⣿⣿⣷⣿⣿⡿⣽⣷⣻⡽⣿⣿⣿⣿⢷⣟⡿⣾⣻⣿⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠻⣿⣿⣿⣾⣿⣿⣿⣿⣿⣿⣿⣿⣿⠃
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠙⠿⢿⣿⣿⣿⣿⠿⠿⠟⠋⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣿⣿⣿⡿⣿⣿⣿⣿⣿⣿⡷⣯⡿⣧⣸⢿⣿⣿⣿⣿⣻⣿⣿⣽⣷⣯⣿⣿⣿⣿⣿⣟⡿⣾⣻⢷⣟⣿⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠙⠻⢿⣿⣿⣿⣿⣿⣿⣿⣿⡿⠁⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢸⣿⣿⣿⣿⡿⣷⣿⣿⣿⣿⣷⡿⣽⢯⣟⡿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣟⡾⣟⣷⢿⣻⣾⣿⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠉⠛⠛⠛⠛⠛⠋⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⣿⣿⣿⣿⣿⣿⣿⣷⣿⣿⣿⡿⣽⣻⢯⣟⣿⣿⠀⠀⠀⠉⣿⣿⣿⣿⣿⣿⣟⡾⣟⣯⣟⣯⣷⢯⣿⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣿⣿⣿⣿⣾⣿⣿⣾⣿⣿⣿⣿⣻⡽⣟⣯⣿⡿⠀⠀⠀⠀⣿⣿⣿⣻⣿⣿⣯⣟⡿⣽⣾⣻⢾⣟⣿⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢸⣿⣿⣿⣯⣿⢿⣷⣿⣿⣟⣾⣽⣻⢯⣿⣿⡇⠀⠀⠀⠀⣿⣿⣿⣿⢿⣿⣷⣻⣽⣟⣾⡽⣿⢾⣿⠇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠸⣿⣿⣿⣿⣻⣿⣿⣿⣟⣾⣻⢾⣽⣟⣿⣿⠇⠀⠀⠀⠀⢸⣿⣿⣿⣿⣿⣿⣯⢷⣯⡷⣿⢯⣿⣿⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢻⣿⣿⣿⡿⣟⣿⣿⣿⣳⡿⣯⡷⣿⣿⣿⠀⠀⠀⠀⠀⠀⣿⣿⣿⣾⣿⣿⣿⣟⣾⣽⣟⣿⣿⡏⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⢿⣿⣿⣿⣿⣿⣿⣿⣿⣽⢷⣿⣿⣿⠏⠀⠀⠀⠀⠀⠀⠈⢿⣿⣿⣯⣿⣿⣿⣿⣾⣿⣿⡿⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠙⢿⣿⣿⣯⣿⣿⣿⣿⣿⣿⠿⠉⠀⠀⠀⠀⠀⠀⠀⠀⠀⠉⠻⠿⢿⡿⠿⠿⠟⠋⠉⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠉⠉⠙⠋⠙⠉⠉⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀""")    
        
        elif count == 200:
            await ctx.send(f"""🏓 Pong! {user_name}, du hast diesen Befehl bereits {count} Mal benutzt.
 
                                ⠀⠀⠀⢠⣾⣷⣦⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
                                ⠀⠀⣰⣿⣿⣿⣿⣷⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
                                ⠀⢰⣿⣿⣿⣿⣿⣿⣷⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
                                ⢀⣿⣿⣿⣿⣿⣿⣿⣿⣿⣷⣦⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
                                ⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣷⣤⣀⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
                                ⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣶⣤⣄⣀⣀⣤⣤⣶⣾⣿⣿⣿⡷
                                ⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡿⠁
                                ⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡿⠁⠀
                                ⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠏⠀⠀⠀
                                ⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠏⠀⠀⠀⠀
                                ⣿⣿⣿⡇⠀⡾⠻⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠁⠀⠀⠀⠀⠀
                                ⣿⣿⣿⣧⡀⠁⣀⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡇⠀⠀⠀⠀⠀⠀
                                ⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡟⠉⢹⠉⠙⣿⣿⣿⣿⣿⠀⠀⠀⠀⠀⠀⠀
                                ⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣷⣀⠀⣀⣼⣿⣿⣿⣿⡟⠀⠀⠀⠀⠀⠀⠀
                                ⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡿⠋⠀⠀⠀⠀⠀⠀⠀⠀
                                ⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡿⠛⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀
                                ⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡿⠛⠀⠤⢀⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀
                                ⣿⣿⣿⣿⠿⣿⣿⣿⣿⣿⣿⣿⠿⠋⢃⠈⠢⡁⠒⠄⡀⠈⠁⠀⠀⠀⠀⠀⠀⠀
                                ⣿⣿⠟⠁⠀⠀⠈⠉⠉⠁⠀⠀⠀⠀⠈⠆⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
                                ⠋⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠘⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀""")
        else:
            await ctx.send("🏓 Pong!")


@bot.command(name="PingPong", aliases=["pingpong","pongping","PongPing"])
async def pingpong_command(ctx):
    ping_score = 0
    pong_score = 0
    max_score = 3
    round_number = 1

    await ctx.send("🏓 Spielstart: Ping vs Pong!")
    await asyncio.sleep(1)

    funny_interrupts = [
        "💥 Der Ball ist gegen die Wand geflogen!",
        "😵 Ein Spieler hat den Ball verfehlt!",
        "🙈 Ein Vogel hat den Ball gestohlen!",
        "🪞 Der Ball hat sich verdoppelt – verwirrend!",
        "🧤 Der Schiedsrichter hat eingegriffen!"
    ]

    while ping_score < max_score and pong_score < max_score:
        await ctx.send(f"🎯 **Runde {round_number}**")
        await asyncio.sleep(0.5)

        await ctx.send("🏓 Ping!")
        await asyncio.sleep(0.5)
        await ctx.send("🏓 Pong!")
        await asyncio.sleep(0.5)

        # Zufällige Unterbrechung (10% Chance)
        if random.random() < 0.1:
            interrupt = random.choice(funny_interrupts)
            await ctx.send(interrupt)
            await asyncio.sleep(1)
            round_number += 1
            continue  # nächste Runde ohne Punkt

        winner = random.choice(["Ping", "Pong"])
        if winner == "Ping":
            ping_score += 1
        else:
            pong_score += 1

        await ctx.send(f"✅ Punkt für **{winner}**!")
        await ctx.send(f"📊 Stand: Ping {ping_score} – {pong_score} Pong")
        await asyncio.sleep(1)

        round_number += 1

    await ctx.send("💥 Der Ball ist heruntergefallen!")
    await asyncio.sleep(1)
    winner = "Ping" if ping_score > pong_score else "Pong"

    update_pingpong_winner(winner)
    await ctx.send(f"🏆 **{winner} gewinnt mit {ping_score}:{pong_score}!** 🎉")



@bot.command()
async def pong(ctx):
    user_name = ctx.author.display_name

    await ctx.send(f"🏓 Pong!, {user_name} :abc: you idiot")

@bot.command()
async def bong(ctx):
    user_name = ctx.author.display_name

    await ctx.send(f"{user_name} stop taking drugs")

@bot.command()
async def pingpongstats(ctx):
    ping_wins = pingpong_counter.get("Ping", 0)
    pong_wins = pingpong_counter.get("Pong", 0)
    await ctx.send(f"📈 **PingPong-Spielstand**\nPing: `{ping_wins}` Siege\nPong: `{pong_wins}` Siege")

# Bot starten
bot.run(token)
