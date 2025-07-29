# Running in Headless Mode on a Linux Server

This document provides instructions for running the Twitch Drops Miner in headless mode on a Linux server. This mode is designed for users who want to run the application on a remote server without a graphical user interface (GUI).

## Prerequisites

*   A Linux server (x86-64) with SSH access.
*   Python 3.10 or higher installed.
*   The user must have a pre-configured `cookies.jar` file from a Windows machine.

## Setup

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/DevilXD/TwitchDropsMiner.git
    cd TwitchDropsMiner
    ```

2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Transfer your `cookies.jar` file:**
    You will need to transfer your `cookies.jar` file from your Windows machine to the `TwitchDropsMiner` directory on your Linux server. You can use `scp` or any other file transfer method to do this.

## Running the Application

To run the application in headless mode, use the `--headless` flag:

```bash
python3 main.py --headless
```

The application will then start running in the background and will output logging information to the console. You can use a terminal multiplexer like `screen` or `tmux` to keep the application running after you disconnect from your SSH session.

### Example with `screen`

1.  **Start a new `screen` session:**
    ```bash
    screen -S twitch-miner
    ```

2.  **Run the application:**
    ```bash
    python3 main.py --headless
    ```

3.  **Detach from the `screen` session:**
    Press `Ctrl+A` followed by `d`.

You can now safely disconnect from your SSH session, and the application will continue to run in the background. To reattach to the `screen` session, use the following command:

```bash
screen -r twitch-miner
```
