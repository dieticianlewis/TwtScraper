import os
import json
import requests
from bs4 import BeautifulSoup
import re
import random

# NOTE: This script does NOT need tweepy or python-dotenv

# --- Configuration (Copied from your main script) ---
PROFILES_TO_TRACK = [
    {
        "username": "alquis"
    },
    {
        "username": "gnnx"
    }
]

API_URL = "https://us-east1-sent-wc254r.cloudfunctions.net/recentSends"
USER_AGENTS = [ "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36" ]

# --- Helper functions (Copied from your main script) ---
def get_user_uid(username):
    profile_url = f"https://sent.bio/{username}"
    print(f"Scraping {profile_url} to find user UID...")
    try:
        headers = {'User-Agent': random.choice(USER_AGENTS)}
        response = requests.get(profile_url, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        meta_tags = soup.find_all('meta', property='og:image')
        if not meta_tags: return None
        for tag in meta_tags:
            if not tag.has_attr('content'): continue
            image_url = tag['content']
            if "public_users" in image_url:
                match = re.search(r"public_users(?:/|%2F)([a-zA-Z0-9]+)(?:/|%2F)", image_url)
                if match:
                    uid = match.group(1)
                    print(f"Successfully found UID for {username}: {uid}")
                    return uid
        print(f"Could not find a user-specific og:image tag for {username}.")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Error fetching page for {username} to get UID: {e}")
        return None

def get_recent_sends(uid, username_for_logging):
    print(f"Fetching data for '{username_for_logging}' (UID: {uid}) from API...")
    sends = []
    payload = {"data": {"receiverUid": uid}}
    headers = {"Content-Type": "application/json", "User-Agent": random.choice(USER_AGENTS)}
    try:
        response = requests.post(API_URL, headers=headers, json=payload, timeout=15)
        response.raise_for_status()
        api_data = response.json()
        sends_list = api_data.get('result', [])
        if not sends_list: return []
        for index, item in enumerate(sends_list):
            sender_name = item.get('sender_name', 'Unknown')
            amount = item.get('amount', 0)
            currency_symbol = item.get('sender_currency_symbol', '$')
            unique_id = f"{sender_name}-{amount}-{currency_symbol}-{index}"
            sends.append(unique_id) # We only need the ID for the state file
        return sends
    except Exception as e:
        print(f"Error in get_recent_sends for {username_for_logging}: {e}")
        return []

# --- Main Logic for Initialization ---
if __name__ == "__main__":
    print("Starting initialization run...")
    final_state_object = {}

    for profile in PROFILES_TO_TRACK:
        username = profile["username"]
        print(f"\n--- Processing profile: {username} ---")
        uid = get_user_uid(username)
        if uid:
            # Get the list of Positional IDs
            send_ids = get_recent_sends(uid, username)
            if send_ids:
                print(f"Found {len(send_ids)} sends to use as baseline for {username}.")
                final_state_object[username] = send_ids
    
    # Print the final JSON object that should be saved
    print("\n\n" + "="*50)
    print("COPY THE JSON BLOCK BELOW AND PASTE IT INTO last_sends.json")
    print("="*50)
    # Use json.dumps for clean, properly formatted output
    print(json.dumps(final_state_object, indent=2))
    print("="*50)