#!/usr/bin/python3
import getpass
import io
import platform
import string
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

arch = platform.machine()
if arch not in ("armv7l", "aarch64"):
    sys.exit(f"System architecture is {arch}, must be one of armv7l, aarch64")

try:
    from apt.cache import Cache as AptCache
except ModuleNotFoundError:
    sys.exit("Cannot import apt module, must run script with system Python")

if sys.version_info < (3, 11):
    vi = sys.version_info
    sys.exit(f"Python version is {vi.major}.{vi.minor}, must run script on 3.11+")

user = getpass.getuser()
if user != "root":
    sys.exit(f"Current user is {user}, must run script as root (e.g. with sudo)")

MEDIAMTX_SOURCES = {
    "armv7l": "https://github.com/bluenviron/mediamtx/releases/download/v1.12.0/mediamtx_v1.12.0_linux_armv7.tar.gz",
    "aarch64": "https://github.com/bluenviron/mediamtx/releases/download/v1.12.0/mediamtx_v1.12.0_linux_arm64v8.tar.gz",
}


def main() -> None:
    check_camera()
    maybe_download_mediamtx()

    apt_cache = AptCache()
    apt_cache.update()
    apt_cache.open()

    maybe_install_nginx(apt_cache)
    update_nginx_config()

    maybe_create_venv()

    update_mediamtx_service()
    update_controller_service()
    restart_services()


def check_camera() -> None:
    output = check_output("rpicam-hello", "--list-cameras")
    if output == "No cameras available!":
        sys.exit("Could not detect Raspberry Pi Camera, aborting")


def maybe_download_mediamtx() -> None:
    if Path("/usr/local/bin/mediamtx").is_file():
        return

    print("Downloading mediamtx...")
    with urllib.request.urlopen(MEDIAMTX_SOURCES[arch]) as response:
        f = io.BytesIO(response.read())

    print("Extracting to /usr/local/bin/...")
    with zipfile.ZipFile(f) as archive:
        archive.extract("mediamtx", "/usr/local/bin")


def maybe_install_nginx(apt_cache: AptCache) -> None:
    nginx = apt_cache["nginx"]
    if not nginx.is_installed:
        print("Installing nginx...")
        nginx.mark_install()
        apt_cache.commit()


def update_nginx_config() -> None:
    default = Path("/etc/nginx/sites-enabled/default")
    if default.is_file():
        print("Removing default nginx site configuration...")
        default.unlink()

    print("Copying nginx configuration to /etc/nginx/sites-available/...")
    sites = Path("etc/nginx/sites-available").iterdir()
    for path in sites:
        content = path.read_text("utf8")
        content = replace_site_substitutions(content)
        dest = Path("/etc/nginx/sites-available").joinpath(path.name)
        dest.write_text(content)

    print("Adding symlinks to /etc/nginx/sites-enabled/...")
    for path in sites:
        dest = Path("/etc/nginx/sites-enabled").joinpath(path.name)
        dest.symlink_to(path)

    print("Reloading nginx...")
    check_call("systemctl", "restart", "nginx")


def replace_site_substitutions(content: str) -> str:
    project_root = Path(__file__).parent
    # Nginx also uses $-placeholders, so we're just going to do safe subsitution.
    return string.Template(content).safe_substitute(
        {
            "PROJECT": project_root,
        }
    )


def maybe_create_venv() -> None:
    if Path(".venv").is_dir():
        return

    print("Creating controller.py virtual environment at .venv/...")
    check_call(sys.executable, "-m", "venv")
    print("Installing controller.py dependencies...")
    check_call(".venv/bin/pip", "install", "-r", "requirements.txt")


def update_mediamtx_service() -> None:
    print("Copying zerobot-mediamtx.service to /etc/systemd/system/...")
    content = Path("etc/systemd/system/zerobot-mediamtx.service").read_text("utf8")
    content = replace_service_substitutions(content)
    Path("/etc/systemd/system/zerobot-mediamtx.service").write_text(content, "utf8")


def update_controller_service() -> None:
    print("Copying zerobot-controller.service to /etc/systemd/system/...")
    content = Path("etc/systemd/system/zerobot-controller.service").read_text("utf8")
    content = replace_service_substitutions(content)
    Path("/etc/systemd/system/zerobot-controller.service").write_text(content, "utf8")


def replace_service_substitutions(content: str) -> str:
    project_root = Path(__file__).parent
    return string.Template(content).substitute(
        {
            "PROJECT": project_root,
            "PYTHON": project_root / ".venv/bin/python",
        }
    )


def restart_services() -> None:
    print("Reloading services...")
    check_call("systemctl", "daemon-reload")

    print("Enabling and restarting zerobot-mediamtx.service...")
    check_call("systemctl", "enable", "zerobot-mediamtx")
    check_call("systemctl", "restart", "zerobot-mediamtx")

    print("Enabling and restarting zerobot-controller.service...")
    check_call("systemctl", "enable", "zerobot-controller")
    check_call("systemctl", "restart", "zerobot-controller")


def check_call(*args: object) -> None:
    str_args = [str(x) for x in args]
    subprocess.check_call(str_args, stdout=subprocess.DEVNULL)


def check_output(*args: object) -> str:
    str_args = [str(x) for x in args]
    return subprocess.check_output(str_args, text=True)


if __name__ == "__main__":
    main()
