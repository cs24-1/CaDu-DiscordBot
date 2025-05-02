import json
import discord
from discord.ext import commands, tasks
import json
import os
import requests
from datetime import datetime, timedelta, date
from dotenv import load_dotenv
import warnings
from urllib3.exceptions import InsecureRequestWarning
from requests.exceptions import RequestException
from datetime import timezone
import pytz

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
            ping_counter = json.load(f)
            ping_counter = {int(k): v for k, v in ping_counter.items()}  # Keys in int konvertieren
    except FileNotFoundError:
        ping_counter = {}

# Speichere aktuelle Zählerstände
def save_ping_counter():
    with open("ping_counter.json", "w") as f:
        json.dump(ping_counter, f)

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

# Hintergrundaufgabe: Stundenplan alle 24h posten
@tasks.loop(hours=24)
async def stundenplan_task():
    channel = bot.get_channel(int(channel_id))
    if channel is None:
        print("❌ Kanal nicht gefunden.")
        return
    
    today = datetime.today()

    if today.weekday() >= 5:  # Teste ob Wochentag
        print("⏭ Wochenende ~ Stundenplan wird nicht gesendet.")
        return

    if today.date() in FEIERTAGE: # Teste ob Feiertag
        print("⏭ Feiertag ~ Stundenplan wird nicht gesendet.")
        return

    stundenplan = hole_stundenplan(0)

    # Aufteilen des Textes in kleinere Nachrichten
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

    # hole aktuelles Datum,
   
    start_date = datetime.now()

    # ZEITRAUM-FILTER HIER
    zeitraum_ende = start_date + timedelta(days=tage)

    gefilterte_eintraege = []  # Liste für gefilterte Einträge
    for eintrag in eintraege:
        start_dt = datetime.fromtimestamp(eintrag["start"])
        if start_date <= start_dt <= zeitraum_ende:
            gefilterte_eintraege.append(eintrag)

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
        else:
            await ctx.send("🏓 Pong!")
                

# Bot starten
bot.run(token)wb