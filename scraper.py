import os
import json
import time
import requests
import tweepy
from dotenv import load_dotenv
import random
from bs4 import BeautifulSoup
import re
from datetime import datetime
from zoneinfo import ZoneInfo

load_dotenv()

# --- Configuration (unchanged) ---
PROFILES_TO_TRACK = [
    {
        "username": "alquis",
        "tweet_message": "Predator Keira @alquis13 just got sent {amount} from pedo {sender_name} at {est_time} EST"
    },
    {
        "username": "gnnx",
        "tweet_message": "Predator Keira's friend @gigiidk18 was sent {amount} from {sender_name} at {est_time} EST"
    }
]

STATE_FILE = "last_sends.json"
API_URL = "https://us-east1-sent-wc254r.cloudfunctions.net/recentSends"
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
]

# --- (get_user_uid is unchanged) ---
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

# --- get_recent_sends returns full send objects ---
def get_recent_sends(uid, username_for_logging):
    print(f"Fetching data for '{username_for_logging}' (UID: {uid}) from API: {API_URL}")
    sends = []
    payload = {"data": {"receiverUid": uid}}
    headers = {"Content-Type": "application/json", "User-Agent": random.choice(USER_AGENTS)}
    try:
        response = requests.post(API_URL, headers=headers, json=payload, timeout=15)
        response.raise_for_status()
        api_data = response.json()
        sends_list = api_data.get('result', [])
        if not sends_list: return []
        
        for item in sends_list:
            sender_name = item.get('sender_name', 'Unknown')
            amount = item.get('amount', 0)
            currency_symbol = item.get('sender_currency_symbol', '$')
            formatted_amount = f"{currency_symbol}{amount}"
            sends.append({
                "sender": sender_name,
                "amount": formatted_amount,
            })
        return sends
    except Exception as e:
        print(f"Error in get_recent_sends for {username_for_logging}: {e}")
        return []

# --- (read_state, write_state, post_to_twitter are unchanged) ---
def read_state():
    if not os.path.exists(STATE_FILE): return {}
    with open(STATE_FILE, 'r') as f:
        try: return json.load(f)
        except json.JSONDecodeError: return {}
def write_state(data):
    with open(STATE_FILE, 'w') as f: json.dump(data, f, indent=2)
def post_to_twitter(message):
    try:
        client = tweepy.Client(
            consumer_key=os.environ['TWITTER_API_KEY'],
            consumer_secret=os.environ['TWITTER_API_SECRET'],
            access_token=os.environ['TWITTER_ACCESS_TOKEN'],
            access_token_secret=os.environ['TWITTER_ACCESS_TOKEN_SECRET']
        )
        response = client.create_tweet(text=message)
        print(f"Tweet posted successfully: {response.data['id']}")
        return True
    except Exception as e:
        print(f"Error posting to Twitter: {e}")
        return False

# --- THE DEFINITIVE MAIN LOGIC USING "SHIFT DETECTION" ---
if __name__ == "__main__":
    print("Starting scraper for all profiles...")
    all_states = read_state()
    something_was_updated = False
    target_timezone = ZoneInfo("America/New_York")

    for profile in PROFILES_TO_TRACK:
        username = profile["username"]
        print(f"\n--- Checking profile: {username} ---")
        uid = get_user_uid(username)
        if not uid: continue
        
        # 1. GET THE NEW LIST OF SENDS
        recent_sends = get_recent_sends(uid, username)
        if not recent_sends: continue
        
        print(f"Found {len(recent_sends)} recent sends for {username}.")
        
        # 2. GET THE OLD LIST OF SENDS FROM MEMORY
        previous_sends = all_states.get(username, [])
        new_sends = []

        if not previous_sends:
            # If we have no memory, everything is new (for the first run)
            new_sends = recent_sends
        else:
            # Find the anchor point: the top-most old send
            anchor_send = previous_sends[0]
            try:
                # Find where the anchor is in the new list
                anchor_index = recent_sends.index(anchor_send)
                # Everything before the anchor is new
                new_sends = recent_sends[:anchor_index]
            except ValueError:
                # The anchor was pushed off the list; assume everything is new
                print("Major list change detected, treating all sends as new.")
                new_sends = recent_sends

        if new_sends:
            print(f"Found {len(new_sends)} new send(s) for {username}! Preparing to tweet.")
            
            now_est = datetime.now(target_timezone)
            time_str = now_est.strftime("%H:%M")
            
            new_sends.reverse() # Tweet oldest new send first
            
            all_tweets_succeeded = True 
            for send in new_sends:
                # Add a unique marker to every tweet to prevent all duplicate errors
                unique_marker = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz', k=2))
                message_template = f"{profile['tweet_message']} [{unique_marker}]"

                final_message = message_template.format(
                    amount=send['amount'],
                    sender_name=send['sender'],
                    est_time=time_str
                )
                print(f"Formatted Tweet: {final_message}")
                
                if not post_to_twitter(final_message):
                     print(f"Stopping processing for {username} due to tweet failure. State will not be updated.")
                     all_tweets_succeeded = False
                     break
                time.sleep(2)
            
            if all_tweets_succeeded:
                # Save the complete new list as our new memory
                all_states[username] = recent_sends
                something_was_updated = True
        else:
            print(f"No new sends detected for {username}.")

    if something_was_updated:
        print("\n--- All profiles checked. Writing updated states to file. ---")
        write_state(all_states)
    else:
        print("\n--- All profiles checked. No new sends found. ---")