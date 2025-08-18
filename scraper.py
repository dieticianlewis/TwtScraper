import os
import json
import requests
import tweepy
from bs4 import BeautifulSoup

# --- Configuration ---
SENT_BIO_URL = "https://sent.bio/alquis"
STATE_FILE = "last_send.json"

# --- Main Functions ---

def get_latest_send():
    """Fetches the sent.bio page and extracts the most recent send."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'}
        response = requests.get(SENT_BIO_URL, headers=headers, timeout=10)
        response.raise_for_status()  # Raises an exception for bad status codes

        soup = BeautifulSoup(response.text, 'html.parser')

        # This is the most crucial part and might need updating if sent.bio changes its website structure.
        # Based on the image, we look for a list of sends. We will target the first item.
        # We need to inspect the page's HTML to find the correct selectors.
        # Let's assume the structure is something like this:
        # <div class="some-container">
        #   <p>Recent Sends</p>
        #   <div>
        #       <span>Anonymous</span>
        #       <span>$200</span>
        #   </div>
        #   ...
        # </div>
        
        # FINDING THE SELECTORS: Right-click on the "Recent Sends" area on the page and click "Inspect".
        # Find the container for the very first send. Find the elements for sender and amount inside it.
        # The selectors below are GUESSES and you will likely need to update them.
        
        # Based on a quick look at sent.bio's structure (as of late 2023), it uses divs.
        # Let's try to find a parent container and then the first child.
        recent_sends_list = soup.find_all('div', class_='p-4') # This is a guess
        
        # A more robust selector might be needed. Let's assume the first 'p-4' div inside a specific parent holds the send info.
        # Let's find the "Recent Sends" header and work from there.
        header = soup.find(lambda tag: tag.name == "p" and "Recent Sends" in tag.text)
        if not header:
            print("Could not find 'Recent Sends' header.")
            return None
        
        # The first sibling div after the header should be the latest send
        first_send_div = header.find_next_sibling('div')
        
        if first_send_div:
            # Inside this div, find the sender name and amount
            # Again, these are educated guesses based on common structures.
            sender_element = first_send_div.find('p', class_='font-semibold')
            amount_element = first_send_div.find('p', class_='text-gray-400') # The amount might be in a different element

            if sender_element and amount_element:
                sender = sender_element.text.strip()
                amount = amount_element.text.strip()
                
                # Create a unique ID for the send to avoid duplicates if amounts/names are the same
                send_id = f"{sender}-{amount}-{first_send_div.text.strip()}"

                return {"sender": sender, "amount": amount, "id": send_id}
        
        print("Could not parse the latest send. HTML structure may have changed.")
        return None

    except requests.exceptions.RequestException as e:
        print(f"Error fetching page: {e}")
        return None
    except Exception as e:
        print(f"An error occurred during scraping: {e}")
        return None


def read_state():
    """Reads the last processed send's ID from the state file."""
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE, 'r') as f:
        return json.load(f)

def write_state(data):
    """Writes the latest send's data to the state file."""
    with open(STATE_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def post_to_twitter(message):
    """Posts a message to Twitter."""
    try:
        # Get secrets from environment variables (provided by GitHub Actions)
        consumer_key = os.environ['TWITTER_API_KEY']
        consumer_secret = os.environ['TWITTER_API_SECRET']
        access_token = os.environ['TWITTER_ACCESS_TOKEN']
        access_token_secret = os.environ['TWITTER_ACCESS_TOKEN_SECRET']
        
        # Use Tweepy for Twitter API v2
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

# --- Main Execution Logic ---

if __name__ == "__main__":
    print("Starting scraper...")
    latest_send = get_latest_send()
    
    if not latest_send:
        print("Could not retrieve latest send. Exiting.")
        exit()

    print(f"Found latest send: {latest_send}")
    
    previous_state = read_state()
    previous_send_id = previous_state.get("id")

    if latest_send["id"] != previous_send_id:
        print("New send detected! Preparing to tweet.")
        
        # Format the tweet message
        sender_name = latest_send['sender']
        amount = latest_send['amount']
        message = f"🎉 New send for alquis! 🎉\n\nFrom: {sender_name}\nAmount: {amount}\n\nCheck it out: {SENT_BIO_URL}"
        
        if post_to_twitter(message):
            print("Updating state file with the new send.")
            write_state(latest_send)
        else:
            print("Failed to post tweet. State file will not be updated.")
            
    else:
        print("No new send detected. Everything is up to date.")