from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import re

app = Flask(__name__)

# --- Google Sheets Setup ---
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("keys/google_credentials.json", scope)
client = gspread.authorize(creds)

# Open your spreadsheet
sheet = client.open("Daily Food Headcount").sheet1

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
        # Default single number to Veg if unspecified
        veg_count = int(numbers[0])

    total_count = veg_count + nonveg_count

    # Get current date details
    today = datetime.datetime.now()
    day_name = today.strftime("%A")
    date_str = today.strftime("%Y-%m-%d")
    timestamp = today.strftime("%H:%M:%S")

    # Check if weekend
    if day_name in ["Saturday", "Sunday"]:
        reply.body(f"🚫 Today is {day_name}. Food tracking is active Mon-Fri only.")
        return str(resp)

    try:
        # Get all existing dates in Column A to check for existing entries today
        dates_in_sheet = sheet.col_values(1)
        
        row_data = [date_str, day_name, veg_count, nonveg_count, total_count, timestamp]

        if date_str in dates_in_sheet:
            # Get index (1-based index in gspread)
            row_index = dates_in_sheet.index(date_str) + 1
            
            # Update existing row range (Columns A to F)
            cell_range = f"A{row_index}:F{row_index}"
            sheet.update(cell_range, [row_data])
            status_text = "🔄 *Headcount Updated!*"
        else:
            # Append new row if today's date doesn't exist
            sheet.append_row(row_data)
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

if __name__ == "__main__":
    app.run(port=5000, debug=True)

app = app

if __name__ == "__main__":
    app.run(port=5000, debug=True)