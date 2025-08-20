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

# --- (get_user_uid function is unchanged) ---
def get_user_uid(username):
    profile_url = f"https://sent.bio/{username}"
    print(f"Scraping {profile_url} to find user UID...")
    try:
        headers = {'User-Agent': random.choice(USER_AGENTS)}
        response = requests.get(profile_url, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        meta_tags = soup.find_all('meta', property='og:image')
        if not meta_tags:
            print(f"Could not find any og:image meta tags for {username}.")
            return None
        for tag in meta_tags:
            if not tag.has_attr('content'): continue
            image_url = tag['content']
            if "public_users" in image_url:
                print(f"DEBUG: Found user-specific image URL: {image_url}")
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

# --- get_recent_sends uses the Positional ID, which is correct for the Snapshot method ---
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
        if not sends_list:
             print(f"API response for {username_for_logging} contained no sends.")
             return []
        
        for index, item in enumerate(sends_list):
            sender_name = item.get('sender_name', 'Unknown')
            amount = item.get('amount', 0)
            currency_symbol = item.get('sender_currency_symbol', '$')
            formatted_amount = f"{currency_symbol}{amount}"
            unique_id = f"{sender_name}-{amount}-{currency_symbol}-{index}"
            
            sends.append({
                "sender": sender_name,
                "amount": formatted_amount,
                "id": unique_id,
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

# --- THE DEFINITIVE MAIN LOGIC USING THE "SNAPSHOT" METHOD ---
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
        
        # 1. GET THE NEW LIST OF SENDS (WITH POSITIONAL IDS)
        recent_sends = get_recent_sends(uid, username)
        if not recent_sends: continue
        
        print(f"Found {len(recent_sends)} recent sends for {username}.")
        
        # 2. GET THE OLD AND NEW SNAPSHOTS (LISTS OF IDs)
        previous_send_ids = set(all_states.get(username, [])) 
        current_send_ids = {send['id'] for send in recent_sends}

        # 3. FIND THE DIFFERENCE TO IDENTIFY TRULY NEW SENDS
        new_sends = [send for send in recent_sends if send['id'] not in previous_send_ids]

        if new_sends:
            print(f"Found {len(new_sends)} new send(s) for {username}! Preparing to tweet.")
            
            now_est = datetime.now(target_timezone)
            time_str = now_est.strftime("%H:%M")

            tweet_counts = {}
            potential_tweets = []
            
            for send in new_sends:
                base_text = profile["tweet_message"].format(
                    amount=send['amount'],
                    sender_name=send['sender'],
                    est_time=time_str
                )
                potential_tweets.append({'base_text': base_text})
                tweet_counts[base_text] = tweet_counts.get(base_text, 0) + 1

            potential_tweets.reverse() # Tweet oldest new send first
            
            # This flag ensures we only update state if all tweets for a user succeed
            all_tweets_succeeded = True 
            for item in potential_tweets:
                base_text = item['base_text']
                final_message = base_text

                if tweet_counts[base_text] > 1:
                    unique_marker = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz', k=2))
                    final_message = f"{base_text} [{unique_marker}]"
                
                print(f"Formatted Tweet: {final_message}")
                
                if not post_to_twitter(final_message):
                     print(f"Stopping processing for {username} due to tweet failure. State will not be updated.")
                     all_tweets_succeeded = False # Mark as failed
                     break # Stop this user's tweets
                time.sleep(2)
            
            # 4. IF ALL TWEETS SUCCEEDED, SAVE THE NEW SNAPSHOT
            if all_tweets_succeeded:
                all_states[username] = list(current_send_ids)
                something_was_updated = True
        else:
            print(f"No new sends detected for {username}.")

    # 5. WRITE THE FINAL, UPDATED STATES TO THE FILE
    if something_was_updated:
        print("\n--- All profiles checked. Writing updated states to file. ---")
        write_state(all_states)
    else:
        print("\n--- All profiles checked. No new sends found. ---")