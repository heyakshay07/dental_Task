import os
import json
import time
from pyngrok import ngrok
from dotenv import set_key, load_dotenv

ENV_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
VAPI_CONFIG_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "vapi_assistant_config.json"))

def update_env(key, value):
    set_key(ENV_PATH, key, value)

load_dotenv(ENV_PATH)

def update_vapi_config(url):
    if os.path.exists(VAPI_CONFIG_PATH):
        with open(VAPI_CONFIG_PATH, "r") as f:
            data = json.load(f)
        
        data["serverUrl"] = f"{url}/webhook/vapi"
        
        with open(VAPI_CONFIG_PATH, "w") as f:
            json.dump(data, f, indent=2)

def start_ngrok():
    print("Starting ngrok tunnel on port 8000...")
    # Open a HTTP tunnel on the default port 8000
    public_url = ngrok.connect(8000).public_url
    print(f"ngrok tunnel created: {public_url}")
    
    # Update .env
    print("Updating .env with NGROK_URL...")
    update_env("NGROK_URL", public_url)
    
    # Update vapi_assistant_config.json
    print("Updating vapi_assistant_config.json with the new serverUrl...")
    update_vapi_config(public_url)
    
    print("\nSetup complete! The URL is exposed and saved.")
    print("Keep this script running to keep the ngrok tunnel alive. Press Ctrl+C to quit.")
    
    try:
        # Keep the ngrok process alive
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nClosing ngrok tunnel...")
        ngrok.kill()

if __name__ == "__main__":
    start_ngrok()
