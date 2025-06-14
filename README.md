# Distortion - Advanced Remote Administration & Security Framework
- Distortion is a sophisticated, proof-of-concept remote administration framework designed for security research and educational purposes. It utilizes Discord as a secure, resilient, and intuitive Command & Control (C2) channel, allowing for real-time interaction with remote endpoints.

- The framework is built on a modular, three-part architecture that separates the initial listener, the agent, and the executor, demonstrating professional software design patterns used in advanced remote systems.

## 🏛️ Architecture
The project's strength lies in its clean separation of concerns, broken down into three core components:

- initiator.py (The Listener): A lightweight, stealthy listener that runs on the target system. Its sole purpose is to establish an event-driven connection to the Discord C2 and wait for an activation command. It is designed for minimal resource usage and a low detection footprint.

- snitch.py (The Agent): The main C2 agent that activates upon receiving a command from the operator. It handles all communication with Discord, manages slash commands, creates dedicated channels for each target, and relays instructions to the executor. It serves as the "brains" of the operation.

- distortion.py (The Executor): A comprehensive library of functions and classes that perform all actions on the host machine. By isolating this "heavy lifting" from the agent, the system remains organized and scalable.

## ✨ Features
Distortion is equipped with a wide array of powerful features, all controllable via intuitive Discord slash commands:

- Full Interactive Shell: A fully stateful remote cmd.exe shell that correctly tracks the current working directory (cd commands work as expected).

- Real-time Audio Streaming: Capture live audio from the target's microphone and stream it directly to a Discord voice channel.

- Media Capture & Exfiltration:

- Take instant screenshots of the entire screen.

- Capture images from the webcam.

- Record screen activity for a specified duration and send it as a high-quality video file.

## Advanced Context-Aware Keylogger:

- An efficient, event-driven keylogger that runs in a background thread.

- Provides context by logging the active window title only when it changes, minimizing performance impact.

- Includes a real-time alerting system that notifies the operator when the user accesses specified applications (e.g., social media).

## Credential Exfiltration: Dumps and decrypts saved passwords from Google Chrome and Microsoft Edge browsers.

## Remote File System Operations:

- Upload any file from the victim's machine to the Discord channel, with checks for file size limits.

- Upload a file from the operator's machine onto the victim's machine at any specified path.

## System & UI Interaction:

- Trigger arbitrary key presses and combinations (e.g., alt+f4, ctrl+c).

- Display a custom native Windows alert box with a specified title and message.

- Retrieve the public IP address and approximate geographic location.

## Destructive Capabilities (for Research):

- A function to demonstrate overwriting the Master Boot Record (MBR).

- Full Stealth & Cleanup:

- A kill switch to cleanly terminate both the agent and the initiator process.

- A self-destruct mechanism that completely erases all project files from the target machine, leaving no trace.

## Setup & Usage
### Prerequisites
- Ensure you have Python installed, then install all required libraries from the provided file:

- `pip install -r requirements.txt`

### Configuration
- Create a Discord Application and a Bot user in the Discord Developer Portal.

- Create a .env file in the project directory and add your bot's token:

- `BOT_TOKEN="YOUR_DISCORD_BOT_TOKEN_HERE"`

- Inside snitch.py, update the GUILD_ID, ALL_VICTIMS_HERE category ID, and CONTROL_CENTER channel ID to match your Discord server setup.

### Deployment & Operation
- Deploy: Place the initiator.py, distortion.py, and snitch.py files on the target machine.

- Execute: Run the initiator.py script. It will connect to Discord and wait silently for an activation command.

- Activate: In your control channel, issue the activation command:

- `$activate <target-hostname>`

### Control: The snitch.py agent will activate, create a dedicated channel for the victim, and is now ready to receive slash commands. Use /help to see the full list of available commands.

### Note: Distortion WILL NOT run on a virtual machine. So make sure to comment out dangerous lines of codes before running it.

## Disclaimer
- This project was developed for educational purposes and advanced security research only. It is a proof-of-concept to demonstrate complex system interactions and C2 architectures. It is intended to be used exclusively in controlled environments, such as penetration testing labs or on systems where you have explicit, authorized permission. The user is solely responsible for their actions. Unauthorized use of this tool on any system is illegal and unethical.

## Contributions:
- Feel free to give your contributions.
