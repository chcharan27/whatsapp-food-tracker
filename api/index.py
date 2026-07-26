from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import re
import pytz
import os
import json

app = Flask(__name__)

# --- Google Sheets Setup ---
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

# Check for environment variable (for Vercel) or local file fallback
creds_json_str = os.environ.get("GOOGLE_CREDENTIALS_JSON")
if creds_json_str:
    creds_dict = json.loads(creds_json_str)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
else:
    creds = ServiceAccountCredentials.from_json_keyfile_name("keys/google_credentials.json", scope)

client = gspread.authorize(creds)
sheet = client.open("Daily Food Headcount").sheet1

# Color definitions (RGB normalized between 0 and 1)
DARK_NAVY = {"red": 0.11, "green": 0.21, "blue": 0.36}   # Month Banner Background
LIGHT_BLUE = {"red": 0.89, "green": 0.93, "blue": 0.98}  # Column Header Background
WHITE = {"red": 1.0, "green": 1.0, "blue": 1.0}

def create_monthly_section(month_year_str):
    """Inserts a merged monthly banner and styled table headers."""
    # 1. Append Month Banner (e.g. "JULY 2026")
    sheet.append_row([month_year_str, "", "", "", "", ""])
    last_row = len(sheet.get_all_values())
    
    # Merge cells across all 6 columns (A to F)
    sheet.merge_cells(f"A{last_row}:F{last_row}")
    
    # Style Month Banner
    sheet.format(f"A{last_row}:F{last_row}", {
        "backgroundColor": DARK_NAVY,
        "textFormat": {"foregroundColor": WHITE, "bold": True, "fontSize": 12},
        "horizontalAlignment": "CENTER",
        "verticalAlignment": "MIDDLE"
    })
    
    # 2. Append Table Headers
    headers = ["Date", "Day", "Veg Count", "Non-Veg Count", "Total Headcount", "Timestamp"]
    sheet.append_row(headers)
    header_row = last_row + 1
    
    # Style Table Headers
    sheet.format(f"A{header_row}:F{header_row}", {
        "backgroundColor": LIGHT_BLUE,
        "textFormat": {"bold": True, "fontSize": 10},
        "horizontalAlignment": "CENTER",
        "verticalAlignment": "MIDDLE"
    })

@app.route("/webhook", methods=["POST"])
def whatsapp_webhook():
    incoming_msg = request.values.get("Body", "").strip().lower()
    
    resp = MessagingResponse()
    reply = resp.message()

    # Parse Veg and Non-Veg counts using Regex
    veg_match = re.search(r'(\d+)\s*(?:v|veg|vegetarian)', incoming_msg)
    nonveg_match = re.search(r'(\d+)\s*(?:nv|non\s*veg|nonveg|chicken|egg)', incoming_msg)

    veg_count = int(veg_match.group(1)) if veg_match else 0
    nonveg_count = int(nonveg_match.group(1)) if nonveg_match else 0

    # Fallback: If no keywords specified, treat single number as Total Veg or prompt user
    if not veg_match and not nonveg_match:
        numbers = re.findall(r'\d+', incoming_msg)
        if not numbers:
            reply.body(
                "⚠️ *Invalid Format!*\n\n"
                "Please specify counts using keywords.\n"
                "👉 *Examples:*\n"
                "• `5 veg 10 nonveg`\n"
                "• `8 veg`\n"
                "• `12 nonveg`"
            )
            return str(resp)
        veg_count = int(numbers[0])

    total_count = veg_count + nonveg_count

    # Get current date details in IST
    ist = pytz.timezone('Asia/Kolkata')
    today = datetime.datetime.now(ist)
    day_name = today.strftime("%A")
    date_str = today.strftime("%Y-%m-%d")
    month_year_str = today.strftime("%B %Y").upper()  # e.g., "JULY 2026"
    timestamp = today.strftime("%H:%M:%S")

    # Check if weekend
    if day_name in ["Saturday", "Sunday"]:
        reply.body(f"🚫 Today is {day_name}. Food tracking is active Mon-Fri only.")
        return str(resp)

    try:
        all_values = sheet.get_all_values()
        
        # Check if current month header exists in Column A
        month_exists = any(row and row[0] == month_year_str for row in all_values)
        
        if not month_exists:
            create_monthly_section(month_year_str)
            all_values = sheet.get_all_values() # Refresh values list

        # Extract Column A values to check for same-day duplicates
        dates_in_sheet = [row[0] if row else "" for row in all_values]
        row_data = [date_str, day_name, veg_count, nonveg_count, total_count, timestamp]

        if date_str in dates_in_sheet:
            # Overwrite existing row for today
            row_index = dates_in_sheet.index(date_str) + 1
            cell_range = f"A{row_index}:F{row_index}"
            sheet.update(cell_range, [row_data])
            status_text = "🔄 *Headcount Updated!*"
        else:
            # Append new record row under current month
            sheet.append_row(row_data)
            last_row = len(sheet.get_all_values())
            
            # Format data alignment
            sheet.format(f"A{last_row}:F{last_row}", {
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

# Expose app object for Vercel Serverless environment
app = app

if __name__ == "__main__":
    app.run(port=5000, debug=True)