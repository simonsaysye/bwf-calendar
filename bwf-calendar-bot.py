import requests
from bs4 import BeautifulSoup
import json
import datetime
import os.path
from dateutil import parser

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ['https://www.googleapis.com/auth/calendar.events']
SERVICE_ACCOUNT_FILE = 'credentials.json'

URL = "https://corporate.bwfbadminton.com/events/calendar/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; BWF-Schedule-Bot/1.0; +https://example.com/contact)"
}

def get_authenticated_service():
    """Builds the Google Calendar API service using a Service Account."""
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return build('calendar', 'v3', credentials=creds)

def scrape_corporate_calendar():
    """Scrapes the BWF website for tournament data."""
    resp = requests.get(URL, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    events = []
    name_keywords = ['sudirman', 'world championships', 'world tour finals']
    category_keyword = 'super'
    # This year needs to be dynamically scraped from the website to be accurate.
    # For now, it's hardcoded based on the provided HTML context.
    current_year = '2025'

    calendar_wrapper = soup.select_one("#ajaxCalender")
    if not calendar_wrapper:
        return events

    for month_div in calendar_wrapper.select(".item-results"):
        month_name_tag = month_div.select_one("h2.bwf-title_under--red")
        if not month_name_tag:
            continue
        month = month_name_tag.get_text(strip=True)

        for row in month_div.select("table.tblResultLanding tr.bg-light-future"):
            cols = row.find_all("td")
            if len(cols) < 7:
                continue

            country = cols[1].get_text(strip=True)
            dates = cols[2].get_text(" ", strip=True)
            name = cols[3].get_text(strip=True)
            category = cols[5].get_text(strip=True)
            city = cols[6].get_text(strip=True)

            detail_row = row.find_next_sibling("tr", class_="tr-tournament-detail")
            prize_money = None
            if detail_row:
                prize_tag = detail_row.select_one(".bwf-button_group .bwf-button")
                if prize_tag:
                    prize_money = prize_tag.get_text(" ", strip=True).replace("PRIZE MONEY", "").strip()

            if category_keyword in category.lower() or any(keyword in name.lower() for keyword in name_keywords):
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

    return events

def create_calendar_events(events, service):
    """Creates Google Calendar events from a list of scraped tournament data."""
    print("Creating Google Calendar events...")
    for event_data in events:
        try:
            date_str = f"{event_data['dates']} {event_data['month']} {event_data['year']}"
            
            date_parts = date_str.split('-')
            start_date_str = date_parts[0].strip() + ' ' + date_parts[1].strip().split(' ', 1)[1] if len(date_parts) > 1 else date_str
            end_date_str = date_parts[-1].strip() if len(date_parts) > 1 else date_str
            
            start_date = parser.parse(start_date_str).date()
            end_date = parser.parse(end_date_str).date()
            
            # The event end date is exclusive, so we add one day to the end date
            end_date = end_date + datetime.timedelta(days=1)
            
            # Conditionally build the description
            description_lines = []
            if event_data['prize_money']:
                description_lines.append(f"Prize Money: {event_data['prize_money']}")
            description = "\n".join(description_lines)

            event = {
                'summary': f"{event_data['name']} ({event_data['category']})",
                'location': f"{event_data['city']}, {event_data['country']}",
                'description': description,
                'start': {
                    'date': start_date.isoformat(),
                },
                'end': {
                    'date': end_date.isoformat(),
                },
            }

            created_event = service.events().insert(calendarId='primary', body=event).execute()
            print(f"Event created: {created_event.get('htmlLink')}")
        
        except HttpError as error:
            print(f"An error occurred: {error}")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")

if __name__ == '__main__':
    try:
        service = get_authenticated_service()
        tournaments = scrape_corporate_calendar()
        if tournaments:
            create_calendar_events(tournaments, service)
        else:
            print("No tournaments found that match the criteria.")
    except Exception as e:
            print(f"An error occurred during the process: {e}")
