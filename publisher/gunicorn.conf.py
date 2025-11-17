
import threading
import asyncio
from publisher import run_finnhub_client

def when_ready(server):
    """Gunicorn hook that runs when the server is ready."""
    server.log.info("Server is ready. Starting background Finnhub client.")

    # Create a new event loop for the background thread
    def run_async_in_thread():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run_finnhub_client())

    # Start the Finnhub client in a daemon thread
    client_thread = threading.Thread(target=run_async_in_thread)
    client_thread.daemon = True
    client_thread.start()

bind = "0.0.0.0:8080"
workers = 1
threads = 2 # 1 for Flask, 1 for the background task
