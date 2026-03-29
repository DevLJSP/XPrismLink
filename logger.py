import json
import os
import datetime

LOG_FILE = "admin_logs.json"
CONFIG_FILE = "admin_config.json"

def get_logs():
    if not os.path.exists(LOG_FILE):
        return []
    with open(LOG_FILE, "r") as f:
        try:
            return json.load(f)
        except:
            return []

def save_log(entry):
    logs = get_logs()
    logs.append(entry)
    # Keep only the last 100 logs so the file doesn't grow huge
    if len(logs) > 100:
        logs = logs[-100:]
    with open(LOG_FILE, "w") as f:
        json.dump(logs, f, indent=4)

def get_config():
    if not os.path.exists(CONFIG_FILE):
        return {}
    with open(CONFIG_FILE, "r") as f:
        try:
            return json.load(f)
        except:
            return {}

def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)

async def log_event(bot, message: str):
    # Construct log string with timestamp
    now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    full_message = f"[{now}] {message}"
    
    # Save to file
    save_log(full_message)
    
    # Attempt to send to discord channel if configured
    config = get_config()
    channel_id = config.get("log_channel_id")
    if channel_id:
        try:
            channel = bot.get_channel(channel_id)
            if channel:
                await channel.send(f"📋 **Log Event:**\n```\n{full_message}\n```")
            else:
                # If channel is not cached, we can try to fetch it, but usually get_channel is fine.
                pass
        except:
            pass
