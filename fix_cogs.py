import os
import re

game_files = [
    "cogs/blackjack.py", "cogs/crash.py", "cogs/hilo.py", "cogs/mines.py", 
    "cogs/plinko.py", "cogs/coins.py", "cogs/wheel.py", "cogs/parlay.py", 
    "cogs/slots.py", "cogs/dice.py", "cogs/roulette.py"
]

for f in game_files:
    if not os.path.exists(f): continue
    with open(f, "r") as file:
        content = file.read()
    
    # Remove any existing @lock_game() lines entirely
    content = re.sub(r"^\s*@lock_game\(\)\s*\n", "", content, flags=re.MULTILINE)

    lines = content.split("\n")
    new_lines = []
    
    # Now we insert @lock_game() strictly one line before "async def command(self, interaction: discord.Interaction"
    # But ONLY for standard app commands, not internal logic
    # Actually, any async def that takes interaction: discord.Interaction in cogs is either a command or a callback
    for line in lines:
        match = re.match(r"^( *)async def ([a-zA-Z0-9_]+)\(self,\s*interaction:\s*discord\.Interaction\b", line)
        if match and "setup" not in line and "play_again_button" not in line:
            indent = match.group(1)
            new_lines.append(indent + "@lock_game()")
        new_lines.append(line)
        
    with open(f, "w") as file:
        file.write("\n".join(new_lines))
print("Fixed locks!")
