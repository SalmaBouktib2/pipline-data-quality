import os
import time
import json
import requests
from flask import Flask
from google.cloud import pubsub_v1

# --- Configuration ---
try:
    GCP_PROJECT_ID = os.environ["GCP_PROJECT_ID"]
    PUBLISH_TOPIC_ID = os.environ["PUBLISH_TOPIC_ID"]
    FINNHUB_API_KEY = os.environ["FINNHUB_API_KEY"]
    EXCHANGE = os.environ.get("FINNHUB_EXCHANGE", "US")
    POLL_INTERVAL_SECONDS = int(os.environ.get("POLL_INTERVAL_SECONDS", 3600))
except KeyError as e:
    raise RuntimeError(f"Missing required environment variable: {e}") from e

# --- Flask App for Health Checks ---
# Gunicorn will run this 'app' object.
app = Flask(__name__)

@app.route('/')
def health_check():
    """Health check endpoint for Cloud Run."""
    return "Publisher is running.", 200

# --- Pub/Sub Publisher ---
publisher = pubsub_v1.PublisherClient()
TOPIC_PATH = publisher.topic_path(GCP_PROJECT_ID, PUBLISH_TOPIC_ID)

def publish_message(data: dict):
    """Publishes a message to the configured Pub/Sub topic."""
    body = json.dumps(data).encode("utf-8")
    try:
        future = publisher.publish(TOPIC_PATH, body)
        future.result(timeout=30)
        print(f"Published message: {data}")
    except Exception as e:
        print(f"CRITICAL: Error publishing to {TOPIC_PATH}: {e}")

def fetch_and_publish_data():
    """
    Fetches data from the Finnhub '/stock/symbol' endpoint and publishes it.
    """
    api_url = f"https://finnhub.io/api/v1/stock/symbol?exchange={EXCHANGE}&token={FINNHUB_API_KEY}"
    print(f"Fetching data from Finnhub API: {api_url}")
    try:
        response = requests.get(api_url, timeout=30)
        response.raise_for_status()
        symbols = response.json()
        if not isinstance(symbols, list):
            print(f"Error: API did not return a list of symbols. Response: {symbols}")
            return
        print(f"Successfully fetched {len(symbols)} symbols from exchange '{EXCHANGE}'.")
        for symbol_data in symbols:
            publish_message(symbol_data)
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data from Finnhub API: {e}")
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON response from API: {e}")

def poll_data_in_background():
    """
    The main polling loop. This function is designed to be run in a background
    thread started by the Gunicorn 'when_ready' hook.
    """
    print("Background polling thread started.")
    while True:
        fetch_and_publish_data()
        print(f"Sleeping for {POLL_INTERVAL_SECONDS} seconds...")
        time.sleep(POLL_INTERVAL_SECONDS)

# No code is run here in the main execution block.
# Gunicorn is responsible for running the 'app' and the 'when_ready' hook
# in gunicorn.conf.py will start the background thread.