import os
import json
import time
import requests
import tweepy
from dotenv import load_dotenv
import random
from bs4 import BeautifulSoup
import re

load_dotenv()

# --- Configuration ---
PROFILES_TO_TRACK = [
    {
        "username": "alquis",
        "tweet_message": "Predator Keira @alquis13 just got sent {amount} from pedo {sender_name}"
    },
    {
        "username": "gnnx",
        "tweet_message": "Predator Keira's friend @gigiidk18 was sent {amount} from {sender_name}"
    }
]

STATE_FILE = "last_sends.json"
API_URL = "https://us-east1-sent-wc254r.cloudfunctions.net/recentSends"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36",
]

# --- Helper Functions ---

def get_user_uid(username):
    """
    Scrapes the user's profile page to find their unique receiverUid
    by searching all og:image meta tags for the user-specific one.
    """
    profile_url = f"https://sent.bio/{username}"
    print(f"Scraping {profile_url} to find user UID...")
    try:
        headers = {'User-Agent': random.choice(USER_AGENTS)}
        response = requests.get(profile_url, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find ALL meta tags with property="og:image"
        meta_tags = soup.find_all('meta', property='og:image')
        
        if not meta_tags:
            print(f"Could not find any og:image meta tags for {username}.")
            return None

        # Loop through them to find the correct one containing the UID
        for tag in meta_tags:
            if not tag.has_attr('content'):
                continue
            
            image_url = tag['content']
            
            # Check if this is the user-specific URL we are looking for
            if "public_users" in image_url:
                print(f"DEBUG: Found user-specific image URL: {image_url}")
                match = re.search(r"public_users(?:/|%2F)([a-zA-Z0-9]+)(?:/|%2F)", image_url)
                if match:
                    uid = match.group(1)
                    print(f"Successfully found UID for {username}: {uid}")
                    return uid # Success! Return the found UID.

        # If the loop finishes without finding the right tag, we fail.
        print(f"Could not find a user-specific og:image tag for {username}.")
        return None

    except requests.exceptions.RequestException as e:
        print(f"Error fetching page for {username} to get UID: {e}")
        return None

def get_recent_sends(uid, username_for_logging):
    """
    Fetches recent sends from the API using the user's UID.
    """
    print(f"Fetching data for '{username_for_logging}' (UID: {uid}) from API: {API_URL}")
    sends = []
    payload = {"data": {"receiverUid": uid}}
    selected_agent = random.choice(USER_AGENTS)
    headers = {"Content-Type": "application/json", "User-Agent": selected_agent}

    try:
        response = requests.post(API_URL, headers=headers, json=payload, timeout=15)
        response.raise_for_status()
        api_data = response.json()
        sends_list = api_data.get('result', [])
        
        if not sends_list:
             print(f"API response for {username_for_logging} contained no sends.")
             return []
        
        for item in sends_list:
            sender_name = item.get('sender_name', 'Unknown')
            amount = item.get('amount', 0)
            currency_symbol = item.get('sender_currency_symbol', '$')
            formatted_amount = f"{currency_symbol}{amount}"
            timestamp = item.get('created_at', str(time.time()))
            unique_id = f"{sender_name}-{amount}-{currency_symbol}-{timestamp}"
            sends.append({"sender": sender_name, "amount": formatted_amount, "id": unique_id})
        
        return sends
        
    except requests.exceptions.RequestException as e:
        print(f"Error during API call for {username_for_logging}: {e}")
        return []
    except json.JSONDecodeError:
        print(f"Error decoding JSON response for {username_for_logging}. Response was: {response.text}")
        return []

def read_state():
    """Reads the entire state file for all profiles."""
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE, 'r') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}

def write_state(data):
    """Writes the entire state dictionary to the file."""
    with open(STATE_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def post_to_twitter(message):
    """Posts a message to Twitter."""
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

# --- Main Execution Logic ---
if __name__ == "__main__":
    print("Starting scraper for all profiles...")
    all_states = read_state()
    something_was_updated = False

    for profile in PROFILES_TO_TRACK:
        username = profile["username"]
        print(f"\n--- Checking profile: {username} ---")

        # Step 1: Get the user's unique ID
        uid = get_user_uid(username)
        if not uid:
            print(f"Could not get UID for {username}. Skipping.")
            continue

        # Step 2: Use the UID to get recent sends
        recent_sends = get_recent_sends(uid, username)
        if not recent_sends:
            continue

        print(f"Found {len(recent_sends)} recent sends for {username}.")
        previous_send_id = all_states.get(username, {}).get("id")
        
        new_sends = []
        for send in recent_sends:
            if send["id"] == previous_send_id:
                break
            new_sends.append(send)
        
        if new_sends:
            print(f"Found {len(new_sends)} new send(s) for {username}! Preparing to tweet.")
            new_sends.reverse() # Tweet oldest to newest
            
            for send in new_sends:
                message_template = profile["tweet_message"]
                message = message_template.format(amount=send['amount'], sender_name=send['sender'])
                print(f"Formatted Tweet: {message}")
                
                # This is the robust logic: only update state after successful tweet
                if post_to_twitter(message):
                    all_states[username] = send # Update state to the one we just tweeted
                    something_was_updated = True
                else:
                    # If tweeting fails, stop processing this user so we can retry next time.
                    print(f"Stopping processing for {username} due to tweet failure.")
                    break # This exits the `for send in new_sends:` loop
                
                time.sleep(2) # Wait 2 seconds between tweets
        else:
            print(f"No new sends detected for {username}.")

    if something_was_updated:
        print("\n--- All profiles checked. Writing updated states to file. ---")
        write_state(all_states)
    else:
        print("\n--- All profiles checked. No new sends found. ---")