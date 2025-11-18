import threading
from publisher import poll_data_in_background

def when_ready(server):
    """Gunicorn hook that runs when the server is ready."""
    server.log.info("Server is ready. Starting background polling thread.")

    # Start the polling function in a daemon thread
    client_thread = threading.Thread(target=poll_data_in_background)
    client_thread.daemon = True
    client_thread.start()

# The following settings are good for a simple Cloud Run service
workers = 1
threads = 2  # One thread for the Flask app, one for the background polling
timeout = 120 # Increased timeout for potentially long-running startup tasks