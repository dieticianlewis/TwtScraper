import os
import json
import time
import requests
import tweepy
from dotenv import load_dotenv
import random
from bs4 import BeautifulSoup

load_dotenv()

# --- Configuration (Unchanged) ---
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
# This is the correct API endpoint for the NEW payload structure
API_URL = "https://us-east1-sent-wc254r.cloudfunctions.net/recentSends"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36",
]

# --- NEW FUNCTION: Step 1 - Get the User's Unique ID from Meta Tags ---
def get_user_uid(username):
    """
    Scrapes the user's profile page to find their unique receiverUid
    from the og:image meta tag.
    """
    profile_url = f"https://sent.bio/{username}"
    print(f"Scraping {profile_url} to find user UID...")
    try:
        headers = {'User-Agent': random.choice(USER_AGENTS)}
        response = requests.get(profile_url, headers=headers, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find the meta tag with property="og:image"
        meta_tag = soup.find('meta', property='og:image')
        
        if not meta_tag or not meta_tag.has_attr('content'):
            print(f"Could not find og:image meta tag for {username}.")
            return None

        image_url = meta_tag['content']
        # The URL looks like: ".../public_users%2F{UID}%2Fimages%2F..."
        # We split the string by the URL-encoded slash '%2F' to isolate the UID
        parts = image_url.split('%2F')
        if len(parts) > 2 and parts[0].endswith('public_users'):
            uid = parts[1]
            print(f"Successfully found UID for {username}: {uid}")
            return uid
        
        print(f"Could not parse UID from image URL for {username}.")
        return None

    except requests.exceptions.RequestException as e:
        print(f"Error fetching page for {username} to get UID: {e}")
        return None

# --- UPDATED FUNCTION: Step 2 - Use the UID to make the API call ---
def get_recent_sends(uid, username_for_logging):
    """
    Fetches recent sends using the user's UID.
    """
    print(f"Fetching data for '{username_for_logging}' (UID: {uid}) from API...")
    sends = []
    
    # This is the payload structure you discovered
    payload = {
        "data": {
            "receiverUid": uid
        }
    }
    
    selected_agent = random.choice(USER_AGENTS)
    headers = {
        "Content-Type": "application/json",
        "User-Agent": selected_agent
    }

    try:
        # Use a POST request with the new payload
        response = requests.post(API_URL, headers=headers, json=payload, timeout=15)
        response.raise_for_status() 
        api_data = response.json()

        # The actual sends are inside a 'result' key
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

            sends.append({
                "sender": sender_name,
                "amount": formatted_amount,
                "id": unique_id
            })
        
        return sends

    except requests.exceptions.RequestException as e:
        print(f"Error during API call for {username_for_logging}: {e}")
        return []
    except json.JSONDecodeError:
        print(f"Error decoding JSON response for {username_for_logging}. Response was: {response.text}")
        return []


# --- (The rest of the file has minor changes to use the new functions) ---
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

# --- Main execution logic now uses the two-step process ---
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
        # Find the point where the new sends start
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
                # UNCOMMENT the line below when you are ready to tweet for real
                # post_to_twitter(message) 
                time.sleep(2) # Wait 2 seconds between tweets
            
            # Save the ID of the absolute newest send
            all_states[username] = recent_sends[0] 
            something_was_updated = True
        else:
            print(f"No new sends detected for {username}.")

    if something_was_updated:
        print("\n--- All profiles checked. Writing updated states to file. ---")
        write_state(all_states)
    else:
        print("\n--- All profiles checked. No new sends found. ---")