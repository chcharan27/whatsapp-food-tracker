from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import re
import pytz
import os
import json

app = Flask(__name__)

# --- Configuration & Security ---
ALLOWED_ADMINS = [
    "whatsapp:+919010982381",
]

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.environ.get("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")

# --- Google Sheets Setup ---
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

def get_google_sheet():
    """Helper to safely fetch sheet connection without crashing cold-starts."""
    creds_json_str = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if creds_json_str:
        creds_dict = json.loads(creds_json_str)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    else:
        creds = ServiceAccountCredentials.from_json_keyfile_name("keys/google_credentials.json", scope)

    client = gspread.authorize(creds)
    return client.open("Daily Food Headcount").sheet1


# Color definitions for Google Sheets formatting
DARK_NAVY = {"red": 0.11, "green": 0.21, "blue": 0.36}   # Month Banner Background
LIGHT_BLUE = {"red": 0.89, "green": 0.93, "blue": 0.98}  # Column Header Background
SUMMARY_GREY = {"red": 0.94, "green": 0.94, "blue": 0.94}# Summary Row Background
WHITE = {"red": 1.0, "green": 1.0, "blue": 1.0}

def parse_month_year(msg_text, default_datetime):
    """
    Parses dynamic month/year inputs like:
    'summary', 'jan 2025', 'april', 'report dec 24', 'monthly summary march 2026'
    Returns formatted string like 'JANUARY 2025' or None if invalid.
    """
    msg_clean = msg_text.lower().strip()

    # Base list of keywords that trigger a summary request
    summary_keywords = ["summary", "report", "monthly summary", "stats"]
    is_summary_request = any(kw in msg_clean for kw in summary_keywords)

    months_map = {
        "jan": "JANUARY", "january": "JANUARY",
        "feb": "FEBRUARY", "february": "FEBRUARY",
        "mar": "MARCH", "march": "MARCH",
        "apr": "APRIL", "april": "APRIL",
        "may": "MAY",
        "jun": "JUNE", "june": "JUNE",
        "jul": "JULY", "july": "JULY",
        "aug": "AUGUST", "august": "AUGUST",
        "sep": "SEPTEMBER", "sept": "SEPTEMBER", "september": "SEPTEMBER",
        "oct": "OCTOBER", "october": "OCTOBER",
        "nov": "NOVEMBER", "november": "NOVEMBER",
        "dec": "DECEMBER", "december": "DECEMBER"
    }

    # Search for a month keyword in message
    matched_month = None
    for token in msg_clean.split():
        if token in months_map:
            matched_month = months_map[token]
            break

    # If no specific month found but user typed a summary keyword, default to current month
    if not matched_month:
        if is_summary_request:
            return default_datetime.strftime("%B %Y").upper()
        return None

    # Search for a year (4 digits or 2 digits)
    year_match = re.search(r'\b(20\d{2}|\d{2})\b', msg_clean)
    if year_match:
        year_str = year_match.group(1)
        if len(year_str) == 2:
            year_str = f"20{year_str}"
    else:
        # Default to current year if omitted
        year_str = default_datetime.strftime("%Y")

    return f"{matched_month} {year_str}"


def create_monthly_section(sheet, month_year_str):
    """Inserts a merged monthly banner and separate styled table headers."""
    # 1. Append Month Banner (e.g., "JULY 2026")
    sheet.append_row([month_year_str, "", "", "", "", ""])
    banner_row = len(sheet.get_all_values())
    
    # Merge cells across all 6 columns for Month Banner
    sheet.merge_cells(f"A{banner_row}:F{banner_row}")
    sheet.format(f"A{banner_row}:F{banner_row}", {
        "backgroundColor": DARK_NAVY,
        "textFormat": {"foregroundColor": WHITE, "bold": True, "fontSize": 12},
        "horizontalAlignment": "CENTER",
        "verticalAlignment": "MIDDLE"
    })
    
    # 2. Append Table Headers
    headers = ["Date", "Day", "Veg Count", "Non-Veg Count", "Total Headcount", "Timestamp"]
    sheet.append_row(headers)
    header_row = banner_row + 1
    
    # Ensure cells in header row are NOT merged
    try:
        sheet.unmerge_cells(f"A{header_row}:F{header_row}")
    except Exception:
        pass  # Safe fallback if already unmerged

    # Style Table Headers
    sheet.format(f"A{header_row}:F{header_row}", {
        "backgroundColor": LIGHT_BLUE,
        "textFormat": {"foregroundColor": {"red": 0.1, "green": 0.1, "blue": 0.1}, "bold": True, "fontSize": 10},
        "horizontalAlignment": "CENTER",
        "verticalAlignment": "MIDDLE"
    })

def compute_monthly_summary(all_values, month_year_str):
    """Calculates total veg, non-veg, combined total, and daily averages for the month."""
    veg_total = 0
    nonveg_total = 0
    days_count = 0

    for row in all_values:
        if len(row) >= 5 and re.match(r'^\d{4}-\d{2}-\d{2}$', row[0]):
            try:
                row_date = datetime.datetime.strptime(row[0], "%Y-%m-%d")
                if row_date.strftime("%B %Y").upper() == month_year_str:
                    veg_total += int(row[2]) if row[2].isdigit() else 0
                    nonveg_total += int(row[3]) if row[3].isdigit() else 0
                    days_count += 1
            except ValueError:
                continue

    total_meals = veg_total + nonveg_total
    avg_veg = round(veg_total / days_count, 1) if days_count > 0 else 0
    avg_nonveg = round(nonveg_total / days_count, 1) if days_count > 0 else 0
    avg_total = round(total_meals / days_count, 1) if days_count > 0 else 0

    return {
        "days": days_count,
        "veg_total": veg_total,
        "nonveg_total": nonveg_total,
        "total_meals": total_meals,
        "avg_veg": avg_veg,
        "avg_nonveg": avg_nonveg,
        "avg_total": avg_total
    }

@app.route("/webhook", methods=["POST"])
def whatsapp_webhook():
    incoming_msg = request.values.get("Body", "").strip().lower()
    sender = request.values.get("From", "")
    
    resp = MessagingResponse()
    reply = resp.message()

    if ALLOWED_ADMINS and sender not in ALLOWED_ADMINS:
        reply.body("⛔ *Access Denied:* You are not authorized to update or query the food headcount.")
        return str(resp)

    ist = pytz.timezone('Asia/Kolkata')
    today = datetime.datetime.now(ist)
    day_name = today.strftime("%A")
    date_str = today.strftime("%Y-%m-%d")
    month_year_str = today.strftime("%B %Y").upper()
    timestamp = today.strftime("%H:%M:%S")

    # Connect to sheet
    try:
        sheet = get_google_sheet()
    except Exception as e:
        reply.body("❌ Database connection error. Please try again later.")
        print(f"Sheet connection error: {e}")
        return str(resp)

    # --- Dynamic Summary Processing ---
    requested_summary_month = parse_month_year(incoming_msg, today)
    if requested_summary_month:
        try:
            all_values = sheet.get_all_values()
            stats = compute_monthly_summary(all_values, requested_summary_month)
            
            if stats["days"] == 0:
                reply.body(f"📊 No entries recorded yet for *{requested_summary_month}*.")
            else:
                reply.body(
                    f"📊 *Monthly Summary — {requested_summary_month}*\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"📅 *Days Recorded:* {stats['days']} days\n\n"
                    f"🥗 *Total Veg:* {stats['veg_total']} (Avg: {stats['avg_veg']}/day)\n"
                    f"🍗 *Total Non-Veg:* {stats['nonveg_total']} (Avg: {stats['avg_nonveg']}/day)\n"
                    f"🍱 *Grand Total:* {stats['total_meals']} meals\n"
                    f"📈 *Daily Average:* ~{stats['avg_total']} people/day"
                )
        except Exception as e:
            reply.body("❌ Failed to calculate summary. Please check server logs.")
            print(f"Error calculating summary: {e}")
        return str(resp)

    if day_name in ["Saturday", "Sunday"]:
        reply.body(f"🚫 Today is {day_name}. Food tracking is active Mon-Fri only.")
        return str(resp)

    cutoff_time = datetime.time(11, 30, 0)
    if today.time() > cutoff_time:
        reply.body(
            f"⏰ *Cut-off Time Passed!*\n\n"
            f"Headcounts must be submitted before *11:30 AM IST*.\n"
            f"Current time: {today.strftime('%I:%M %p IST')}"
        )
        return str(resp)

    veg_match = re.search(r'(\d+)\s*(?:v|veg|vegetarian)', incoming_msg)
    nonveg_match = re.search(r'(\d+)\s*(?:nv|non\s*veg|nonveg|chicken|egg)', incoming_msg)

    veg_count = int(veg_match.group(1)) if veg_match else 0
    nonveg_count = int(nonveg_match.group(1)) if nonveg_match else 0

    if not veg_match and not nonveg_match:
        numbers = re.findall(r'\d+', incoming_msg)
        if not numbers:
            reply.body(
                "⚠️ *Invalid Format!*\n\n"
                "Please specify counts using keywords or request a summary.\n"
                "👉 *Examples:*\n"
                "• `5 veg 10 nonveg`\n"
                "• `8 veg`\n"
                "• `summary` (current month)\n"
                "• `Jan 2025` or `summary april`"
            )
            return str(resp)
        veg_count = int(numbers[0])

    total_count = veg_count + nonveg_count

    try:
        all_values = sheet.get_all_values()

        # 1. Ensure current month header exists
        month_exists = any(row and len(row) > 0 and row[0].strip().upper() == month_year_str for row in all_values)
        if not month_exists:
            create_monthly_section(sheet, month_year_str)
            all_values = sheet.get_all_values()  # Refresh rows after appending header

        # 2. Build row data
        row_data = [date_str, day_name, veg_count, nonveg_count, total_count, timestamp]

        # 3. Check if today's date already exists in Column A
        dates_in_sheet = [row[0].strip() if row else "" for row in all_values]

        if date_str in dates_in_sheet:
            row_index = dates_in_sheet.index(date_str) + 1
            sheet.update(f"A{row_index}:F{row_index}", [row_data])
            status_text = "🔄 *Headcount Updated!*"
        else:
            sheet.append_row(row_data)
            new_row_index = len(all_values) + 1
            sheet.format(f"A{new_row_index}:F{new_row_index}", {
                "horizontalAlignment": "CENTER",
                "verticalAlignment": "MIDDLE"
            })
            status_text = "🟢 *Headcount Recorded!*"

        reply.body(
            f"{status_text}\n\n"
            f"📅 *Date:* {date_str} ({day_name})\n"
            f"🥗 *Veg:* {veg_count}\n"
            f"🍗 *Non-Veg:* {nonveg_count}\n"
            f"📊 *Total Headcount:* {total_count} people"
        )
    except Exception as e:
        reply.body("❌ Failed to save to database. Please check server logs.")
        print(f"Error updating/appending sheet: {e}")

    return str(resp)


# Automated Daily Reminder Endpoint
@app.route("/send-reminder", methods=["GET", "POST"])
def send_reminder():
    """Triggered automatically by Vercel Cron at 10:00 AM IST weekdays."""
    
    auth_header = request.headers.get("Authorization")
    cron_secret = os.environ.get("CRON_SECRET")

    # Explicit check for presence and match
    if not cron_secret or auth_header != f"Bearer {cron_secret}":
        return {"error": "Unauthorized"}, 401

    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        return {"status": "error", "message": "Twilio API keys missing."}, 500

    twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    
    reminder_text = (
        "🔔 *Daily Food Headcount Reminder*\n\n"
        "Good morning! Please reply with today's lunch headcount before *11:30 AM IST*.\n"
        "👉 *Example:* `5 veg 10 nonveg`"
    )

    sent_count = 0
    for admin_phone in ALLOWED_ADMINS:
        try:
            twilio_client.messages.create(
                from_=TWILIO_WHATSAPP_NUMBER,
                body=reminder_text,
                to=admin_phone
            )
            sent_count += 1
        except Exception as e:
            print(f"Failed to send reminder to {admin_phone}: {e}")

    return {"status": "success", "reminders_sent": sent_count}, 200


if __name__ == "__main__":
    app.run(port=5000, debug=True)
