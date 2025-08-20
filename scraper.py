import os
import json
import time
import requests
import tweepy
from dotenv import load_dotenv

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

# --- NEW: This function calls the API directly ---
def get_recent_sends(username):
    """
    Fetches the recent sends for a user directly from the API.
    Returns a list of send dictionaries, newest first.
    """
    print(f"Fetching data for '{username}' from API...")
    sends = []
    
    payload = {"username": username}
    headers = {
        "Content-Type": "application/json",
        "Origin": "https://sent.bio",
        "Referer": f"https://sent.bio/{username}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    try:
        response = requests.post(API_URL, headers=headers, json=payload, timeout=15)
        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
        
        api_data = response.json() # This is the list like [{sender_name: ...}, ...]

        # --- Convert API data to the format our script expects ---
        for index, item in enumerate(api_data):
            sender_name = item.get('sender_name', 'Unknown')
            amount = item.get('amount', 0)
            currency_symbol = item.get('sender_currency_symbol', '$')
            
            formatted_amount = f"{currency_symbol}{amount}"
            
            # Create a unique ID to prevent tweeting duplicates.
            # Including the index makes it unique even if the same person sends the same amount twice in a row.
            unique_id = f"{sender_name}-{amount}-{currency_symbol}-{index}"

            sends.append({
                "sender": sender_name,
                "amount": formatted_amount,
                "id": unique_id
            })
        
        return sends

    except requests.exceptions.RequestException as e:
        print(f"Error fetching API for {username}: {e}")
        return []
    except json.JSONDecodeError:
        print(f"Error decoding JSON response for {username}. Response was: {response.text}")
        return []

# --- Helper Functions (Unchanged) ---
def read_state():
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE, 'r') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}

def write_state(data):
    with open(STATE_FILE, 'w') as f:
        json.dump(data, f, indent=2)

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

# --- Main Logic (Unchanged from multi-send version) ---
if __name__ == "__main__":
    print("Starting scraper for all profiles...")
    all_states = read_state()
    something_was_updated = False

    for profile in PROFILES_TO_TRACK:
        username = profile["username"]
        print(f"\n--- Checking profile: {username} ---")

        recent_sends = get_recent_sends(username)
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
            new_sends.reverse() # Tweet oldest new send first
            
            for send in new_sends:
                message_template = profile["tweet_message"]
                message = message_template.format(amount=send['amount'], sender_name=send['sender'])
                
                print(f"Formatted Tweet: {message}")
                post_to_twitter(message)
                time.sleep(2)

            all_states[username] = recent_sends[0] # Save the newest send as the last seen
            something_was_updated = True
        else:
            print(f"No new sends detected for {username}.")

    if something_was_updated:
        print("\n--- All profiles checked. Writing updated states to file. ---")
        write_state(all_states)
    else:
        print("\n--- All profiles checked. No new sends found. ---")