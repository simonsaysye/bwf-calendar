import requests
from bs4 import BeautifulSoup
import datetime
from dateutil import parser
from dateutil.relativedelta import relativedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/calendar.events', 'https://www.googleapis.com/auth/calendar.readonly']
SERVICE_ACCOUNT_FILE = 'credentials.json'
CALENDAR_ID = 'aecf58ddb7d31c04819a9ad9bdd718a17609f236da31215d1ce7d08861ffefdc@group.calendar.google.com'

URL = "https://corporate.bwfbadminton.com/events/calendar/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; BWF-Schedule-Bot/1.0; +https://example.com/contact)"
}

def get_authenticated_service():
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return build('calendar', 'v3', credentials=creds)

def scrape_corporate_calendar():
    try:
        resp = requests.get(URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as e:
        print("Error fetching page:", e)
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    events = []
    
    name_keywords = ['sudirman', 'world championships', 'world tour finals']
    category_keyword = 'super'
    current_year = '2025'

    calendar_wrapper = soup.select_one("#ajaxCalender")
    if not calendar_wrapper:
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

    return events

def create_calendar_events(events, service):
    print("Creating Google Calendar events...")
    for event_data in events:
        try:
            date_str = f"{event_data['dates']} {event_data['month']} {event_data['year']}"
            date_str = " ".join(date_str.split())
            date_parts = date_str.split('-')
            
            if len(date_parts) > 1:
                start_part = date_parts[0].strip()
                end_part = date_parts[1].strip()
                
                # Parse start date
                start_date_str = f"{start_part} {event_data['month']} {event_data['year']}"
                start_date = parser.parse(start_date_str).date()

                # Parse end date
                if not any(c.isalpha() for c in end_part):  # no month in end
                    end_date_str = f"{end_part} {event_data['month']} {event_data['year']}"
                    end_date = parser.parse(end_date_str).date()
                else:  # month present in end
                    end_date_str = f"{end_part} {event_data['year']}"
                    end_date = parser.parse(end_date_str).date()
                
                # Adjust if end_date < start_date and tournament < 10 days
                if end_date < start_date:
                    end_date += relativedelta(months=1)
            
            else:
                start_date = parser.parse(date_str).date()
                end_date = start_date

            # Make end date exclusive
            end_date_exclusive = end_date + datetime.timedelta(days=1)

            # Check if event already exists
            existing_events = service.events().list(
                calendarId=CALENDAR_ID,
                q=event_data['name'],
                timeMin=start_date.isoformat() + 'T00:00:00Z',
                timeMax=end_date_exclusive.isoformat() + 'T00:00:00Z',
                singleEvents=True,
                orderBy='startTime'
            ).execute()

            if existing_events.get('items'):
                print(f"Skipping: '{event_data['name']}' already exists.")
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
            print(f"Created: {event_data['name']} ({start_date} - {end_date})")

        except Exception as e:
            print(f"Error creating event '{event_data['name']}': {e}")

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
