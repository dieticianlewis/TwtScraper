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

# --- (get_recent_sends is unchanged) ---
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

# --- THE DEFINITIVE MAIN LOGIC WITH UID CACHING AND ROBUST SHIFT DETECTION ---
if __name__ == "__main__":
    print("Starting scraper for all profiles...")
    all_states = read_state()
    something_was_updated = False
    target_timezone = ZoneInfo("America/New_York")

    for profile in PROFILES_TO_TRACK:
        username = profile["username"]
        print(f"\n--- Checking profile: {username} ---")

        # 1. GET THE USER'S STATE AND UID (with caching)
        user_state = all_states.get(username, {"uid": None, "sends": []})
        uid = user_state.get("uid")

        if not uid:
            print(f"UID for {username} not in state file, fetching from web...")
            uid = get_user_uid(username)
            if uid:
                user_state["uid"] = uid # Save the fetched UID
                all_states[username] = user_state # Ensure the user_state is in the main dict
                something_was_updated = True # Mark state as dirty to save the new UID
            else:
                print(f"Could not get UID for {username}. Skipping.")
                continue

        # 2. GET THE NEW LIST OF SENDS FROM API
        recent_sends = get_recent_sends(uid, username)
        if not recent_sends:
            print(f"No sends returned from API for {username}. Skipping.")
            continue
        
        print(f"Found {len(recent_sends)} recent sends for {username}.")
        
        # 3. GET THE OLD LIST OF SENDS FROM MEMORY
        previous_sends = user_state.get("sends", [])
        
        # 4. ROBUSTLY DETECT NEW SENDS
        # Make a mutable copy of the old sends to "check them off"
        unseen_sends = list(previous_sends)
        new_sends = []

        # Iterate through the new sends to see which ones are unaccounted for.
        # Note: The API returns sends newest-first, so this will find new sends
        # in the order they appear on the site.
        for send in recent_sends:
            try:
                # If the send exists in our old list, remove one instance of it
                unseen_sends.remove(send)
            except ValueError:
                # If .remove() fails, it's because this send was not in the
                # old list. Therefore, it is a new send.
                new_sends.append(send)

        if new_sends:
            print(f"Found {len(new_sends)} new send(s) for {username}! Preparing to tweet.")
            
            now_est = datetime.now(target_timezone)
            time_str = now_est.strftime("%H:%M")
            
            # Tweet oldest new send first. Since our list is newest-first, we reverse it.
            new_sends.reverse() 
            
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
                time.sleep(2) # Brief pause between tweets
            
            if all_tweets_succeeded:
                # Save the complete new list as our new memory for sends
                user_state["sends"] = recent_sends
                all_states[username] = user_state
                something_was_updated = True
        else:
            print(f"No new sends detected for {username}.")

    if something_was_updated:
        print("\n--- All profiles checked. Writing updated states to file. ---")
        write_state(all_states)
    else:
        print("\n--- All profiles checked. No new sends or UIDs found. ---")