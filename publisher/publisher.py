
import os
import asyncio
import json
import websockets
from flask import Flask
from google.cloud import pubsub_v1

# --- Configuration ---
try:
    GCP_PROJECT_ID = os.environ["GCP_PROJECT_ID"]
    PUBLISH_TOPIC_ID = os.environ["PUBLISH_TOPIC_ID"]
    DEAD_LETTER_TOPIC_ID = os.environ["DEAD_LETTER_TOPIC_ID"]
    FINNHUB_API_KEY = os.environ["FINNHUB_API_KEY"]
except KeyError as e:
    raise RuntimeError(f"Missing required environment variable: {e}") from e

# --- Health Check Web Server ---
app = Flask(__name__)
@app.route('/')
def health_check():
    return "OK", 200

# --- Pub/Sub Publisher ---
publisher = pubsub_v1.PublisherClient()
MAIN_TOPIC_PATH = publisher.topic_path(GCP_PROJECT_ID, PUBLISH_TOPIC_ID)
DEAD_LETTER_TOPIC_PATH = publisher.topic_path(GCP_PROJECT_ID, DEAD_LETTER_TOPIC_ID)

def publish_message(data: dict):
    body = json.dumps(data).encode("utf-8")
    try:
        future = publisher.publish(MAIN_TOPIC_PATH, body)
        future.result()
        print(f"Published message to {MAIN_TOPIC_PATH}: {data}")
    except Exception as e:
        print(f"Error publishing to {MAIN_TOPIC_PATH}: {e}")
        print(f"Sending message to dead-letter topic {DEAD_LETTER_TOPIC_PATH}...")
        try:
            future = publisher.publish(DEAD_LETTER_TOPIC_PATH, body)
            future.result()
            print(f"Successfully sent to dead-letter topic: {data}")
        except Exception as dl_e:
            print(f"CRITICAL: Failed to publish to dead-letter topic: {dl_e}")

# --- Finnhub WebSocket Client ---
async def run_finnhub_client():
    """
    Connects to the Finnhub WebSocket API and continuously listens for trades.
    Includes a retry mechanism to handle disconnections.
    """
    uri = f"wss://ws.finnhub.io?token={FINNHUB_API_KEY}"
    while True:  # Infinite loop to handle reconnection
        try:
            print(f"Connecting to Finnhub WebSocket at {uri}...")
            async with websockets.connect(uri) as websocket:
                print("Connection successful. Subscribing to trades...")
                # Subscribe to a 24/7 cryptocurrency stream for testing
                await websocket.send('{"type":"subscribe","symbol":"BINANCE:BTCUSDT"}')
                # You can switch back to AAPL during market hours if you wish
                # await websocket.send('{"type":"subscribe","symbol":"AAPL"}')

                async for message in websocket:
                    data = json.loads(message)
                    if data.get("type") == "trade":
                        for trade in data.get("data", []):
                            publish_message(trade)
                    elif data.get("type") == "ping":
                        print("Received ping from server.")
                    else:
                        print(f"Received non-trade message: {data}")

        except (websockets.exceptions.ConnectionClosedError, websockets.exceptions.ConnectionClosedOK) as e:
            print(f"WebSocket connection closed: {e}. Reconnecting in 15 seconds...")
        except Exception as e:
            print(f"An unexpected error occurred: {e}. Reconnecting in 15 seconds...")

        await asyncio.sleep(15)  # Wait before trying to reconnect
