import os
import json
import time
import requests
import tweepy
from dotenv import load_dotenv
import random

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
# --- THIS IS THE CORRECT API ENDPOINT ---
# Note the "{}" which we will fill with the username.
API_URL_TEMPLATE = "https://us-east1-sent-wc254r.cloudfunctions.net/getUserProfile?username={}"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36",
]

def get_recent_sends(username):
    """
    Fetches user profile data from the correct API endpoint and extracts recent sends.
    """
    # --- THIS IS THE FIX ---
    # We format the URL with the username and make a GET request (no payload).
    url = API_URL_TEMPLATE.format(username)
    print(f"Fetching data for '{username}' from API: {url}")
    sends = []
    
    selected_agent = random.choice(USER_AGENTS)
    print(f"Using User-Agent: {selected_agent}")

    headers = {
        "User-Agent": selected_agent
    }

    try:
        # Use a GET request now, which has no payload (json= parameter is gone)
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status() 
        
        profile_data = response.json()

        # The sends are located inside the 'recentSends' key in the response
        api_sends = profile_data.get('recentSends', [])
        if not api_sends:
            print(f"No 'recentSends' data found in API response for {username}.")
            return []

        # Convert API data to the format our script expects
        for index, item in enumerate(api_sends):
            sender_name = item.get('sender_name', 'Unknown')
            amount = item.get('amount', 0)
            currency_symbol = item.get('sender_currency_symbol', '$')
            formatted_amount = f"{currency_symbol}{amount}"
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

# --- (The rest of the file is unchanged) ---
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
            new_sends.reverse()
            for send in new_sends:
                message_template = profile["tweet_message"]
                message = message_template.format(amount=send['amount'], sender_name=send['sender'])
                print(f"Formatted Tweet: {message}")
                post_to_twitter(message)
                time.sleep(2)
            all_states[username] = recent_sends[0]
            something_was_updated = True
        else:
            print(f"No new sends detected for {username}.")

    if something_was_updated:
        print("\n--- All profiles checked. Writing updated states to file. ---")
        write_state(all_states)
    else:
        print("\n--- All profiles checked. No new sends found. ---")