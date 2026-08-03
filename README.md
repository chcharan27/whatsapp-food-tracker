# 🥗 Daily Food Headcount WhatsApp Bot

A Flask-based backend server that automates daily office meal headcount tracking via WhatsApp (Twilio API) and stores structured records directly in Google Sheets using the Google Drive & Sheets APIs. It also includes automated daily reminders via Vercel Cron.

---

## 📌 Project Overview

* **Automated Data Entry:** Intercepts incoming WhatsApp messages containing meal preferences (e.g., `5 veg 10 nonveg`) and logs them in Google Sheets.
* **Monthly Layout & Formatting:** Automatically groups entries by month, generates styled monthly banner headers, creates table headers, and formats daily total rows.
* **Cut-off & Weekend Restrictions:** Enforces submission deadlines (before 11:30 AM IST) and ignores tracking on weekends.
* **Monthly Summaries:** Responds with total meal counts and daily averages when an authorized admin requests a `summary`.
* **Cron Reminders:** Sends automated morning WhatsApp reminders to admins every weekday at 10:00 AM IST.

---

## 🏗️ Project Architecture & Tech Stack

* **Language:** Python 3.9+
* **Framework:** Flask
* **Services & APIs:**
  * **Twilio WhatsApp API:** Message routing & webhook processing.
  * **Google Sheets API (`gspread`):** Real-time spreadsheet data logging & cell formatting.
  * **Pytz:** Timezone handling (`Asia/Kolkata`).
  * **Vercel:** Cloud deployment & scheduled cron jobs.

---

## 📁 Repository Structure

```text
├── app.py                  # Main Flask application logic & webhook handlers
├── requirements.txt        # Python dependencies
├── vercel.json             # Vercel deployment & Cron configuration
└── keys/
    └── google_credentials.json  # (Local only) Service Account credentials
    
    
install packages: winget install ngrok/ngrok
twilio recovery code:7C3GL1BCGEFH2K4CYS6XK2KB



Sand box: https://wasabi-confined-shrink.ngrok-free.dev/webhook

To run: ngrk http 5000

🚀 Local Development 

Setup
1. Clone the RepositoryBash
    git clone [https://github.com/your-username/food-headcount-bot.git](https://github.com/your-username/food-headcount-bot.git)
    cd food-headcount-bot

2. Create a Virtual Environment & Install DependenciesBashpython -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    pip install -r requirements.txt

3. Requirements (requirements.txt)Plaintextflask
    twilio
    gspread
    oauth2client
    pytz

4. Run the Local ServerBashpython app.py
    The Flask application will start at http://127.0.0.1:5000.🔗 Webhook Configuration (Twilio)Use ngrok to expose your local Flask server to the internet during development:Bashngrok http 5000
    Copy the forwarding URL provided by ngrok (e.g., https://xxxx.ngrok-free.app).In the Twilio Console, go to WhatsApp Sandbox Settings.Paste your URL into WHEN A MESSAGE COMES IN:https://xxxx.ngrok-free.app/webhook (Method: HTTP POST).Save settings.☁️ Deployment on Vercel1. vercel.json SetupCreate a vercel.json file in the project root to handle routing and cron schedules:JSON{
    "builds": [
        {
        "src": "app.py",
        "use": "@vercel/python"
        }
    ],
    "routes": [
        {
        "src": "/(.*)",
        "dest": "app.py"
        }
    ],
    "crons": [
        {
        "path": "/send-reminder",
        "schedule": "30 4 * * 1-5"
        }
    ]
    }
(Note: 30 4 * * 1-5 UTC corresponds to 10:00 AM IST on Weekdays)2. Deploy via Vercel CLIBashvercel --prod
Update your Twilio Webhook URL to point to your live Vercel production domain:https://your-project.vercel.app/webhook📱 WhatsApp Commands & UsageCommand / MessageDescriptionExample<veg> veg <nonveg> nonvegLogs/updates daily headcount5 veg 10 nonveg<number> vegLogs veg headcount only8 vegsummary / reportFetches current monthly stats & averagessummary