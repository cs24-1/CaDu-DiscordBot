# Function to fetch the timetable
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import warnings
from utils import constants
import pytz
import requests
from requests import RequestException
from urllib3.exceptions import InsecureRequestWarning

def get_timetable(days):
    """Fetch and format the timetable from Campus Dual self-service system.

    This function retrieves class schedules from the Campus Dual API and formats them
    into a readable Discord message. It handles time zone conversion and groups entries by date.

    Args:
        days (int): Number of days to fetch the schedule for:
            - 0: Today's schedule only
            - 1: Tomorrow's schedule only
            - n > 1: Schedule for the next n days

    Returns:
        str: A formatted string containing the timetable with:
            - 📅 Date headers (Day of week, DD.MM.YYYY)
            - 📚 Class descriptions
            - 🕒 Start and end times (24h format)
            - 🏫 Room numbers
            Entries are displayed in two columns for better readability.
            Returns an info message if no schedule is found.

    Environment Variables:
        CAMPUS_USER: Campus Dual user ID
        CAMPUS_HASH: Campus Dual authentication hash
    """
    url = f"https://selfservice.campus-dual.de/room/json?userid={constants.Secrets.CAMPUS_USER}&hash={constants.Secrets.CAMPUS_HASH}"

    # Ignore SSL certificate warnings (unsafe, temporary only)
    warnings.simplefilter("ignore", InsecureRequestWarning)
    
    try:
        # SSL verification disabled and timeout added
        response = requests.get(url, verify=False)  # 10 second timeout
        response.raise_for_status()  # Ensure status code is 200

        # Check if the response was successful
        if response.status_code != 200:
            return f"❌ Error while fetching the timetable. Errorcode: {response.status_code}"

        data = response.json()
    except RequestException as e:
        # further errorhandling: all possible network-/connection errors
        return f"❌Error while fetching: {str(e)}"
    except ValueError:
        return "❌ invalid JSON-Response from server."
    except Exception as e:
        return f"❌ unexpected Error: {e}"

    entries = data if isinstance(data, list) else data.get("entries", [])

    if not entries:
        return "ℹ️ No timetable found."

    # Timezone Berlin
    berlin = pytz.timezone("Europe/Berlin")
    now = datetime.now(tz=berlin)
    today_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # 1) Set time window
    if days == 0:
        start_date   = today_midnight
        period_end = today_midnight + timedelta(days=1)
    elif days == 1:
        start_date   = today_midnight + timedelta(days=1)
        period_end = start_date + timedelta(days=1)
    else:
        start_date   = today_midnight
        period_end = today_midnight + timedelta(days=days)

    # 2) Filter (Timestamp → UTC → Berlin)
    filtered_entries = []
    for e in entries:
        start_dt = datetime.fromtimestamp(e["start"], tz=timezone.utc).astimezone(berlin)
        if start_date <= start_dt < period_end:
            filtered_entries.append(e)

    if not filtered_entries:
        if days == 0:
            return "ℹ️ No timetable found for today."
        elif days == 1:
            return "ℹ️ No timetable found for tomorrow."
        return f"ℹ️ No timetable found for the next {days} days."

    output = f"📅 **Timetable for {'today' if days == 0 else 'tomorrow' if days == 1 else 'the next ' + str(days) + ' days'}**\n\n"
    
    # Group by date
    days_grouped = {}
    for entry in filtered_entries:
        start_dt = datetime.fromtimestamp(entry["start"])
        date = start_dt.strftime("%A, %d.%m.%Y")  # Date format "Monday, 29.04.2025"
        
        if date not in days_grouped:
            days_grouped[date] = []
        
        days_grouped[date].append(entry)

    # Now display the timetable by days side by side
    for date, entries in days_grouped.items():
        output += f"📌 **{date}**:\n"
        for i, entry in enumerate(entries):
            berlin = pytz.timezone("Europe/Berlin")
            start_dt = datetime.fromtimestamp(entry["start"], tz=timezone.utc).astimezone(berlin)
            end_dt = datetime.fromtimestamp(entry["end"], tz=timezone.utc).astimezone(berlin)
            start = start_dt.strftime("%H:%M")  # Time in 24h format
            end = end_dt.strftime("%H:%M")  # Time in 24h format
            title = entry["title"]

            # Format display side by side
            if i % 2 == 0:  # First column
                output += f"📚 {entry['description']}\n"
                output += f"🕒 {start}–{end}\n"
                output += f"🏫 Room: {entry['room']}\n"
                output += f"\n"
            else:  # Second column
                output += f"📚 {entry['description']}\n"
                output += f"🕒 {start}–{end}\n"
                output += f"🏫 Room: {entry['room']}\n"
                output += f"\n"
        
        output += "\n"

    return output.strip()


