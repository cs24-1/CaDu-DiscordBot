import os
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

class Secrets:
    DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
    GUILD_ID = int(os.getenv("GUILD_ID"))
    CAMPUS_HASH = os.getenv("CAMPUS_HASH")
    CAMPUS_USER = os.getenv("CAMPUS_USER")

class ChannelIDs:
    QUOTE_CHANNEL_ID = int(os.getenv("CHANNEL_ID"))

class TimeConstants:
    HOLIDAYS = {
        datetime(2025, 1, 1).date(),    # Neujahr 
        datetime(2025, 4, 18).date(),   # Karfreitag
        datetime(2025, 4, 21).date(),   # Ostermontag
        datetime(2025, 5, 1).date(),    # Tag der Arbeit
        datetime(2025, 5, 29).date(),   # Christi Himm
        datetime(2025, 6, 9).date(),    # Pfingstmontag
        datetime(2025, 10, 3).date(),   # Tag der Deutschen Einheit
        datetime(2025, 12, 25).date(),  # 1. Weihnachtstag
        datetime(2025, 12, 26).date(),  # 2. Weihnachtstag
    }