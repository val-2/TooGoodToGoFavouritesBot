import time
import requests
import os
import json
from tgtg import TgtgClient

# === Configuration ==========================
# Replace with your list of user emails
EMAILS = ["valerio.dimaggio@gmail.com", "another.user@example.com"]

# --- Location settings ---
LATITUDE = 48.126      # Replace with your latitude
LONGITUDE = -1.723     # Replace with your longitude
RADIUS = 10            # Radius in kilometers

# --- Telegram Bot settings ---
TELEGRAM_BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
# By default, notification is sent to each user's configured chat id.
TELEGRAM_CHAT_ID = "YOUR_TELEGRAM_CHAT_ID"

# --- Polling settings ---
POLL_INTERVAL_SECONDS = 5  # How often to check (in seconds)

def login(email: str):
    cred_file = f"credentials_{email}.json"
    if os.path.exists(cred_file):
        with open(cred_file, "r") as f:
            creds = json.load(f)
        return TgtgClient(
            access_token=creds["access_token"],
            refresh_token=creds["refresh_token"],
            cookie=creds["cookie"]
        )
    else:
        client = TgtgClient(email=email)
        creds = client.get_credentials()
        with open(cred_file, "w") as f:
            json.dump(creds, f)
        return client

# Setup Clients and notified bags per user
clients = {email: login(email) for email in EMAILS}
notified_bags = {email: set() for email in EMAILS}

# === Telegram Notification Function =========
def send_telegram_notification(message):
    """
    Send a message via Telegram Bot API.
    """
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
    }
    try:
        response = requests.post(url, data=payload)
        if response.status_code == 200:
            print("Telegram notification sent!")
        else:
            print(f"Failed to send notification, status: {response.status_code}\nResponse: {response.text}")
    except Exception as e:
        print(f"Exception while sending telegram notification: {e}")

# === Favorite Bag Checker ====================
total_requests = 0

def check_user_favorite_bag(email, client):
    global total_requests
    total_requests += 1
    print(f"\n=== Request #{total_requests} for {email} ===")
    try:
        items = client.get_items(
            favorites_only=True,
            latitude=LATITUDE,
            longitude=LONGITUDE,
            radius=RADIUS,
        )
    except Exception as e:
        print(f"Error fetching items for {email}: {e}")
        return

    if not items:
        print(f"No items received for {email}.")
        return

    for item in items:
        item_id = item.get("item", {}).get("item_id")
        items_available = item.get("items_available", 0)
        bag_title = item.get("item", {}).get("display_name", "Your favorite bag")
        print(f"User {email}: '{bag_title}' has {items_available} available.")
        if items_available > 0 and item_id not in notified_bags[email]:
            message = (f"Good news!\n\n"
                       f"'{bag_title}' is available: {items_available} bag(s) left.\n"
                       f"Hurry up and grab it!")
            send_telegram_notification(message)
            notified_bags[email].add(item_id)
        elif items_available == 0 and item_id in notified_bags[email]:
            notified_bags[email].remove(item_id)

# === Main Loop ================================
def main():
    print("Starting multi-user favorite bag checker. Press Ctrl+C to exit.")
    while True:
        for email, client in clients.items():
            check_user_favorite_bag(email, client)
        time.sleep(POLL_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()
