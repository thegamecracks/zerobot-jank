# Zerobot

![](/docs/images/robot.jpg)
![](/docs/images/dashboard.jpg)

## Software

This repository comprises of the following components:
- A websocket server to receive movement input, [controller.py](/controller.py)
- An installer script, [install.py](/install.py)
- A [MediaMTX] configuration file to stream Raspberry Pi Camera over WebRTC
- A [Nginx] configuration file to host the web dashboard
- Systemd service files

[MediaMTX]: https://github.com/bluenviron/mediamtx
[Nginx]: https://nginx.org/en/

## System Requirements

The project must run on Raspberry Pi 12 (Bookworm) or newer, whether 32-bit or 64-bit.
The distribution should have the following `apt` packages pre-installed,
but if not, you must download them before running the installer script:
- `python3-venv`
- `rpicam-apps`

## Installation

1. Update the system and reboot:

    ```sh
    $ sudo apt update
    $ sudo apt upgrade
    $ sudo reboot
    ```

2. Clone this repository:

    ```sh
    $ sudo apt install git
    $ git clone https://github.com/thegamecracks/zerobot-jank
    $ cd zerobot-jank
    ```

3. Run install.py as root:

    ```sh
    $ sudo ./install.py
    ```

   If your Raspberry Pi image is 32-bit, you may need to run this command instead:

   ```sh
   $ sudo ./install.py --force-mediamtx-arch armv7l
   ```

The installer should perform the following operations:
1. Verify that your camera can be detected by the Raspberry Pi's modern camera stack
   - If you're stuck here, see ["What to do if your camera is not detected"]
2. Download the `mediamtx` binary to `/usr/local/bin` (only if not present)
3. Install the `nginx` and `python3-dev` packages (only if not present)
4. Copy the web dashboard's files to `/var/www/html/zerobot/`
5. Add or update the nginx site configuration at `/etc/nginx/sites-*/`
6. Create a Python virtual environment in this project directory
   and install packages from `requirements.txt` (only if not present)
7. Add or update these systemd services, `zerobot-controller` and `zerobot-mediamtx`,
   to `/etc/systemd/system/`
8. Reload the systemd daemon and restart the above services

["What to do if your camera is not detected"]: https://forums.raspberrypi.com/viewtopic.php?t=362707

If needed, you can re-run the installer to refresh the configuration files and services.
You can also run `sudo ./install.py --dry-run` to see what operations the script would
perform without modifying your system.

> [!WARNING]
> After installation, make sure this repository is not deleted until this project's
> services are stopped, as they execute files from the project repository directly.
> You may also consider cloning this repository as the root user to ensure other
> users cannot tamper with the project files.

> [!CAUTION]
> Avoid using this robot on a public network, as there is no authentication required
> to access the dashboard or camera feed. Consider installing a firewall to prevent
> unauthorized TCP connections on port 22 (SSH), port 80 (HTTP), and port 8889 (WebRTC).
