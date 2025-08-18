import os
import json
import requests
import tweepy
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

# --- NEW: Configuration for multiple profiles ---
# We now use a list of dictionaries. You can easily add more people here.
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

# The state file will now store the last send for ALL profiles.
STATE_FILE = "last_sends.json" # Note the plural name now

# --- Helper Functions (Mostly Unchanged) ---

def get_latest_send(username):
    """
    Fetches the sent.bio page for a SPECIFIC USERNAME and extracts the most recent send.
    """
    url = f"https://sent.bio/{username}"
    print(f"Fetching data from: {url}")
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        
        header = soup.find(lambda tag: tag.name == "p" and "Recent Sends" in tag.text)
        if not header:
            print(f"Could not find 'Recent Sends' header for {username}.")
            return None
        
        first_send_div = header.find_next_sibling('div')
        
        if first_send_div:
            sender_element = first_send_div.find('p', class_='font-semibold')
            amount_element = first_send_div.find('p', class_='text-gray-400')

            if sender_element and amount_element:
                sender = sender_element.text.strip()
                amount = amount_element.text.strip()
                send_id = f"{sender}-{amount}-{first_send_div.text.strip()}"
                return {"sender": sender, "amount": amount, "id": send_id}
        
        print(f"Could not parse the latest send for {username}. HTML structure may have changed.")
        return None

    except requests.exceptions.RequestException as e:
        print(f"Error fetching page for {username}: {e}")
        return None
    except Exception as e:
        print(f"An error occurred during scraping for {username}: {e}")
        return None

def read_state():
    """Reads the entire state file for all profiles."""
    if not os.path.exists(STATE_FILE):
        return {} # Return an empty dictionary if the file doesn't exist
    with open(STATE_FILE, 'r') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {} # Return empty dict if file is empty or corrupted

def write_state(data):
    """Writes the entire state dictionary to the file."""
    with open(STATE_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def post_to_twitter(message):
    """Posts a message to Twitter."""
    try:
        consumer_key = os.environ['TWITTER_API_KEY']
        consumer_secret = os.environ['TWITTER_API_SECRET']
        access_token = os.environ['TWITTER_ACCESS_TOKEN']
        access_token_secret = os.environ['TWITTER_ACCESS_TOKEN_SECRET']
        
        client = tweepy.Client(
            consumer_key=consumer_key,
            consumer_secret=consumer_secret,
            access_token=access_token,
            access_token_secret=access_token_secret
        )

        response = client.create_tweet(text=message)
        print(f"Tweet posted successfully: {response.data['id']}")
        return True
    except Exception as e:
        print(f"Error posting to Twitter: {e}")
        return False

# --- NEW: Main Execution Logic with a Loop ---

if __name__ == "__main__":
    print("Starting scraper for all profiles...")
    all_states = read_state()
    something_was_updated = False

    # Loop through each profile defined in our configuration
    for profile in PROFILES_TO_TRACK:
        username = profile["username"]
        print(f"\n--- Checking profile: {username} ---")

        latest_send = get_latest_send(username)
        if not latest_send:
            continue # Skip to the next profile if we couldn't get data

        print(f"Found latest send for {username}: {latest_send}")
        
        # Get the previous send ID specifically for this user
        previous_send_id = all_states.get(username, {}).get("id")

        if latest_send["id"] != previous_send_id:
            print(f"New send detected for {username}! Preparing to tweet.")
            
            # Format the custom tweet message for this user
            sender_name = latest_send['sender']
            amount = latest_send['amount']
            message_template = profile["tweet_message"]
            message = message_template.format(amount=amount, sender_name=sender_name)
            
            print(f"Formatted Tweet: {message}")

            if post_to_twitter(message):
                # Update the state in our dictionary for this specific user
                all_states[username] = latest_send
                something_was_updated = True
            else:
                print(f"Failed to post tweet for {username}. State will not be updated.")
        else:
            print(f"No new send detected for {username}.")

    # After checking all profiles, write the updated states back to the file if anything changed.
    if something_was_updated:
        print("\n--- All profiles checked. Writing updated states to file. ---")
        write_state(all_states)
    else:
        print("\n--- All profiles checked. No new sends found. ---")