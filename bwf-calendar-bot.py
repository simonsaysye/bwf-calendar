import os
import datetime
from dateutil import parser
from dateutil.relativedelta import relativedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import logging

# ----------------------------
# Logging setup
# ----------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("scraper.log")
    ]
)

# ----------------------------
# Configuration via environment variables
# ----------------------------
SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "credentials.json")
CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID")

if not CALENDAR_ID:
    logging.error("Environment variable GOOGLE_CALENDAR_ID not set!")
    raise ValueError("GOOGLE_CALENDAR_ID not set!")

URL = "https://corporate.bwfbadminton.com/events/calendar/"

# ----------------------------
# Google Calendar authentication
# ----------------------------
def get_authenticated_service():
    try:
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=[
                'https://www.googleapis.com/auth/calendar.events',
                'https://www.googleapis.com/auth/calendar.readonly'
            ]
        )
        return build('calendar', 'v3', credentials=creds)
    except Exception as e:
        logging.error(f"Failed to authenticate with Google Calendar: {e}")
        raise

# ----------------------------
# Scrape BWF corporate calendar using Playwright
# ----------------------------
def scrape_corporate_calendar():
    logging.info("Fetching BWF corporate calendar with Playwright...")
    events = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(URL)
            html = page.content()
            browser.close()
    except Exception as e:
        logging.error(f"Error fetching page via Playwright: {e}")
        return events

    soup = BeautifulSoup(html, "html.parser")

    name_keywords = ['sudirman', 'world championships', 'world tour finals']
    category_keyword = 'super'
    current_year = '2025'

    calendar_wrapper = soup.select_one("#ajaxCalender")
    if not calendar_wrapper:
        logging.warning("Calendar wrapper not found in HTML.")
        return events

    for month_div in calendar_wrapper.select(".item-results"):
        month_name_tag = month_div.select_one("h2")
        if not month_name_tag:
            continue
        month = month_name_tag.get_text(strip=True)

        for row in month_div.select("table.tblResultLanding tr[class^='bg-']"):
            cols = row.find_all("td")
            if len(cols) < 7:
                continue

            country = cols[1].get_text(strip=True)
            dates = cols[2].get_text(" ", strip=True)

            name_tag = cols[3].select_one("div.name a")
            name = name_tag.get_text(strip=True) if name_tag else cols[3].get_text(strip=True)

            category = cols[5].get_text(strip=True)
            city = cols[6].get_text(strip=True)

            prize_money = None
            detail_row = row.find_next_sibling("tr", class_="tr-tournament-detail")
            if detail_row:
                prize_tag = detail_row.select_one(".bwf-button_group .bwf-button")
                if prize_tag:
                    prize_money = prize_tag.get_text(" ", strip=True).replace("PRIZE MONEY", "").strip()

            if category_keyword.lower() in category.lower() or any(k.lower() in name.lower() for k in name_keywords):
                events.append({
                    "name": name,
                    "dates": dates,
                    "month": month,
                    "country": country,
                    "city": city,
                    "category": category,
                    "prize_money": prize_money,
                    "year": current_year
                })

    logging.info(f"Scraping complete. Found {len(events)} matching tournaments.")
    return events

# ----------------------------
# Create Google Calendar events
# ----------------------------
def create_calendar_events(events, service):
    logging.info("Creating Google Calendar events...")
    for event_data in events:
        try:
            date_str = f"{event_data['dates']} {event_data['month']} {event_data['year']}"
            date_str = " ".join(date_str.split())
            date_parts = date_str.split('-')

            if len(date_parts) > 1:
                start_part = date_parts[0].strip()
                end_part = date_parts[1].strip()

                start_date = parser.parse(f"{start_part} {event_data['month']} {event_data['year']}").date()

                if not any(c.isalpha() for c in end_part):
                    end_date = parser.parse(f"{end_part} {event_data['month']} {event_data['year']}").date()
                else:
                    end_date = parser.parse(f"{end_part} {event_data['year']}").date()

                if end_date < start_date:
                    end_date += relativedelta(months=1)
            else:
                start_date = parser.parse(date_str).date()
                end_date = start_date

            end_date_exclusive = end_date + datetime.timedelta(days=1)

            existing_events = service.events().list(
                calendarId=CALENDAR_ID,
                q=event_data['name'],
                timeMin=start_date.isoformat() + 'T00:00:00Z',
                timeMax=end_date_exclusive.isoformat() + 'T00:00:00Z',
                singleEvents=True,
                orderBy='startTime'
            ).execute()

            if existing_events.get('items'):
                logging.info(f"Skipped: '{event_data['name']}' already exists.")
                continue

            description = f"Prize Money: {event_data['prize_money']}" if event_data['prize_money'] else None

            event = {
                'summary': f"{event_data['name']} ({event_data['category']})",
                'location': f"{event_data['city']}, {event_data['country']}",
                'description': description,
                'start': {'date': start_date.isoformat()},
                'end': {'date': end_date_exclusive.isoformat()},
            }

            service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
            logging.info(f"Created event: '{event_data['name']}' ({start_date} - {end_date})")

        except Exception as e:
            logging.error(f"Error creating event '{event_data['name']}': {e}")

# ----------------------------
# Main
# ----------------------------
if __name__ == '__main__':
    logging.info("Starting BWF Calendar scraper script...")
    try:
        service = get_authenticated_service()
        tournaments = scrape_corporate_calendar()
        if tournaments:
            create_calendar_events(tournaments, service)
        else:
            logging.info("No tournaments found that match the criteria.")
        logging.info("Script finished successfully.")
    except Exception as e:
        logging.error(f"An error occurred during the process: {e}")
