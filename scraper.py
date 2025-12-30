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
        "tweet_message": "Keira @alquis13 just got sent {amount} from {sender_name} at {est_time} EST"
    },
    {
        "username": "gnnx",
        "tweet_message": "Keira's friend @gigiidk18 was sent {amount} from {sender_name} at {est_time} EST"
    },
    {
        "username": "lili",
        "tweet_message": "Predator Julia Lacharity @liliisperfect just got sent {amount} from {sender_name} at {est_time} EST"
    }
]

STATE_FILE = "last_sends.json"
API_URL = "https://us-east1-sent-wc254r.cloudfunctions.net/recentSends"
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
]
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 5

# --- (All helper functions are unchanged) ---
def get_user_uid(username):
    profile_url = f"https://sent.bio/{username}"
    print(f"Scraping {profile_url} to find user UID...")
    for attempt in range(MAX_RETRIES):
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
            print(f"Attempt {attempt + 1}/{MAX_RETRIES} failed for get_user_uid({username}): {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY_SECONDS)
    print(f"All {MAX_RETRIES} attempts failed for get_user_uid({username}).")
    return None

def get_recent_sends(uid, username_for_logging):
    print(f"Fetching data for '{username_for_logging}' (UID: {uid}) from API...")
    for attempt in range(MAX_RETRIES):
        try:
            payload = {"data": {"receiverUid": uid}}
            headers = {"Content-Type": "application/json", "User-Agent": random.choice(USER_AGENTS)}
            response = requests.post(API_URL, headers=headers, json=payload, timeout=15)
            response.raise_for_status()
            api_data = response.json()
            sends_list = api_data.get('result', [])
            sends = []
            if not sends_list: return []
            for item in sends_list:
                sender_name = item.get('sender_name', 'Unknown')
                amount = item.get('amount', 0)
                currency_symbol = item.get('sender_currency_symbol', '$')
                formatted_amount = f"{currency_symbol}{amount}"
                sends.append({"sender": sender_name, "amount": formatted_amount})
            return sends
        except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
            print(f"Attempt {attempt + 1}/{MAX_RETRIES} failed for get_recent_sends({username_for_logging}): {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY_SECONDS)
    print(f"All {MAX_RETRIES} attempts failed for get_recent_sends({username_for_logging}).")
    return []

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

# --- REFACTORED LOGIC FOR A SINGLE PROFILE (WITH SMARTER DUPLICATE DETECTION) ---
def process_profile(profile, all_states, target_timezone):
    username = profile["username"]
    print(f"\n--- Checking profile: {username} ---")

    user_state = all_states.get(username, {"uid": None, "sends": []})
    uid = user_state.get("uid")
    state_was_updated_for_this_user = False

    if not uid:
        print(f"UID for {username} not in state file, fetching from web...")
        uid = get_user_uid(username)
        if uid:
            user_state["uid"] = uid
            all_states[username] = user_state
            state_was_updated_for_this_user = True
        else:
            print(f"Could not get UID for {username}. Skipping.")
            return False

    recent_sends = get_recent_sends(uid, username)
    if not recent_sends:
        print(f"No sends returned from API for {username}. Skipping.")
        return False
    print(f"Found {len(recent_sends)} recent sends for {username}.")
    
    previous_sends = user_state.get("sends", [])
    unseen_sends = list(previous_sends)
    new_sends = []
    for send in recent_sends:
        try: unseen_sends.remove(send)
        except ValueError: new_sends.append(send)

    if new_sends:
        print(f"Found {len(new_sends)} new send(s) for {username}! Preparing to tweet.")
        now_est = datetime.now(target_timezone)
        time_str = now_est.strftime("%H:%M")
        
        # --- THIS IS THE NEW, SMARTER DUPLICATE DETECTION LOGIC ---
        tweet_counts = {}
        potential_tweets = []
        for send in new_sends:
            base_text = profile["tweet_message"].format(
                amount=send['amount'],
                sender_name=send['sender'],
                est_time=time_str
            )
            potential_tweets.append({'base_text': base_text, 'original_send': send})
            tweet_counts[base_text] = tweet_counts.get(base_text, 0) + 1
        
        potential_tweets.reverse() # Tweet oldest new send first
        all_tweets_succeeded = True
        for item in potential_tweets:
            base_text = item['base_text']
            send_data = item['original_send'] # We don't use this but it's good practice
            final_message = base_text
            
            # Only add the unique marker if this text appears more than once IN THIS BATCH
            if tweet_counts[base_text] > 1:
                unique_marker = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz', k=2))
                final_message = f"{base_text} [{unique_marker}]"

            print(f"Formatted Tweet: {final_message}")
            if not post_to_twitter(final_message):
                print(f"Stopping processing for {username} due to tweet failure. State will not be updated.")
                all_tweets_succeeded = False
                break
            time.sleep(2)
        
        if all_tweets_succeeded:
            user_state["sends"] = recent_sends
            all_states[username] = user_state
            state_was_updated_for_this_user = True
    else:
        print(f"No new sends detected for {username}.")
    
    return state_was_updated_for_this_user

# --- MAIN EXECUTION BLOCK (Now much cleaner) ---
if __name__ == "__main__":
    print("Starting scraper for all profiles...")
    all_states = read_state()
    global_state_was_updated = False
    target_timezone = ZoneInfo("America/New_York")

    for profile in PROFILES_TO_TRACK:
        if process_profile(profile, all_states, target_timezone):
            global_state_was_updated = True

    if global_state_was_updated:
        print("\n--- All profiles checked. Writing updated states to file. ---")
        write_state(all_states)
    else:
        print("\n--- All profiles checked. No new sends or UIDs found. ---")
