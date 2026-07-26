from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import re

app = Flask(__name__)

# --- Google Sheets Setup ---
# Setup scope and connect using service account JSON credentials file
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("keys/google_credentials.json", scope)
client = gspread.authorize(creds)

# Open your spreadsheet (must share sheet with service account email)
sheet = client.open("Daily Food Headcount").sheet1

# --- Menu Logic ---
WEEKDAY_MENU = {
    "Monday": "Veg",
    "Tuesday": "Egg",
    "Wednesday": "Non-Veg (Chicken)",
    "Thursday": "Veg",
    "Friday": "Non-Veg (Chicken)",
}

@app.route("/webhook", methods=["POST"])
def whatsapp_webhook():
    incoming_msg = request.values.get("Body", "").strip()
    sender = request.values.get("From", "")
    
    resp = MessagingResponse()
    reply = resp.message()

    # Extract digits from message (e.g., "Today 10" or "10 people" or "10")
    numbers = re.findall(r'\d+', incoming_msg)
    
    if not numbers:
        reply.body(" Please send a valid number. Example: '10' or 'Today 8'")
        return str(resp)
    
    headcount = int(numbers[0])
    
    # Get current date details
    today = datetime.datetime.now()
    day_name = today.strftime("%A")
    date_str = today.strftime("%Y-%m-%d")
    
    # Check if weekend
    if day_name in ["Saturday", "Sunday"]:
        reply.body(f" Today is {day_name}. Food tracking is active Mon-Fri only.")
        return str(resp)
    
    menu_item = WEEKDAY_MENU.get(day_name, "Unknown")
    
    try:
        # Append row: Date, Day, Menu Type, Headcount, Timestamp
        sheet.append_row([
            date_str,
            day_name,
            menu_item,
            headcount,
            today.strftime("%H:%M:%S")
        ])
        
        reply.body(
            f" *Headcount Recorded!*\n\n"
            f" *Date:* {date_str} ({day_name})\n"
            f" *Menu:* {menu_item}\n"
            f" *Headcount:* {headcount} people"
        )
    except Exception as e:
        reply.body(" Failed to save to database. Please check server logs.")
        print(f"Error appending to sheet: {e}")

    return str(resp)

if __name__ == "__main__":
    app.run(port=5000, debug=True)