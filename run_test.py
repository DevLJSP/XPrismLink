import subprocess
import time

p = subprocess.Popen(["$HOME/Desktop/python/DiscordBots/RugLink/Desperation/venv/bin/python3", "main.py"], stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
time.sleep(15)
p.terminate()
stdout, stderr = p.communicate()
print("STDOUT:", stdout)
print("STDERR:", stderr)
