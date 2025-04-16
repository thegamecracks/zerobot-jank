#!/usr/bin/python3
import argparse
import getpass
import io
import platform
import string
import subprocess
import sys
import tarfile
import urllib.request
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
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print actions that would be taken",
    )
    parser.add_argument(
        "--skip-camera",
        action="store_true",
        help="Continue when camera is undetected",
    )

    args = parser.parse_args()
    dry_run: bool = args.dry_run
    skip_camera: bool = args.skip_camera

    check_camera(skip_camera=skip_camera)
    maybe_download_mediamtx(dry_run=dry_run)

    apt_cache = AptCache()
    update_apt(apt_cache, dry_run=dry_run)
    apt_cache.open()

    maybe_install_nginx(apt_cache, dry_run=dry_run)
    update_nginx_config(dry_run=dry_run)

    maybe_create_venv(dry_run=dry_run)

    update_mediamtx_service(dry_run=dry_run)
    update_controller_service(dry_run=dry_run)
    restart_services(dry_run=dry_run)


def check_camera(*, skip_camera: bool) -> None:
    output = check_output("rpicam-hello", "--list-cameras")
    if output != "No cameras available!":
        print("Raspberry Pi camera detected")
    elif skip_camera:
        print("Raspberry Pi camera not detected, ignoring.")
    else:
        sys.exit(
            "Raspberry Pi camera not detected, aborting.\n"
            "If you really want to continue setup, re-run this script "
            "with the --skip-camera flag."
        )


def maybe_download_mediamtx(*, dry_run: bool) -> None:
    if Path("/usr/local/bin/mediamtx").is_file():
        return
    elif dry_run:
        return print("Would download mediamtx to /usr/local/bin/")

    print("Downloading mediamtx...")
    with urllib.request.urlopen(MEDIAMTX_SOURCES[arch]) as response:
        f = io.BytesIO(response.read())

    print("Extracting to /usr/local/bin/...")
    with tarfile.TarFile(fileobj=f, mode="r:gz") as archive:
        archive.extract("mediamtx", "/usr/local/bin")


def update_apt(apt_cache: AptCache, *, dry_run: bool) -> None:
    if dry_run:
        print("Would update apt package index")
    else:
        print("Updating apt package index...")
        apt_cache.update()


def maybe_install_nginx(apt_cache: AptCache, *, dry_run: bool) -> None:
    nginx = apt_cache["nginx"]
    if nginx.is_installed:
        return
    elif dry_run:
        print("Would install nginx")
    else:
        print("Installing nginx...")
        nginx.mark_install()
        apt_cache.commit()


def update_nginx_config(*, dry_run: bool) -> None:
    default = Path("/etc/nginx/sites-enabled/default")
    if not default.is_file():
        pass
    elif dry_run:
        print("Would remove default nginx site configuration")
    else:
        print("Removing default nginx site configuration...")
        default.unlink()

    sites = list(Path("etc/nginx/sites-available").iterdir())
    if not sites:
        pass
    elif dry_run:
        print("Would copy nginx configuration to /etc/nginx/sites-available/")
        print("Would add symlinks to /etc/nginx/sites-enabled/")
        print("Would reload nginx")
    else:
        print("Copying nginx configuration to /etc/nginx/sites-available/...")
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


def maybe_create_venv(*, dry_run: bool) -> None:
    if Path(".venv").is_dir():
        return
    elif dry_run:
        return print("Would create controller.py virtual environment")

    print("Creating controller.py virtual environment at .venv/...")
    check_call(sys.executable, "-m", "venv")
    print("Installing controller.py dependencies...")
    check_call(".venv/bin/pip", "install", "-r", "requirements.txt")


def update_mediamtx_service(*, dry_run: bool) -> None:
    if dry_run:
        return print("Would copy zerobot-mediamtx.service to /etc/systemd/system/")

    print("Copying zerobot-mediamtx.service to /etc/systemd/system/...")
    content = Path("etc/systemd/system/zerobot-mediamtx.service").read_text("utf8")
    content = replace_service_substitutions(content)
    Path("/etc/systemd/system/zerobot-mediamtx.service").write_text(content, "utf8")


def update_controller_service(*, dry_run: bool) -> None:
    if dry_run:
        return print("Would copy zerobot-controller.service to /etc/systemd/system/")

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


def restart_services(*, dry_run: bool) -> None:
    if dry_run:
        return print("Would reload and restart services")

    print("Reloading services...")
    check_call("systemctl", "daemon-reload")

    print("Enabling services...")
    check_call("systemctl", "enable", "zerobot-mediamtx", "zerobot-controller")

    print("Restarting services...")
    check_call("systemctl", "restart", "zerobot-mediamtx", "zerobot-controller")


def check_call(*args: object) -> None:
    str_args = [str(x) for x in args]
    subprocess.check_call(str_args, stdout=subprocess.DEVNULL)


def check_output(*args: object) -> str:
    str_args = [str(x) for x in args]
    return subprocess.check_output(str_args, text=True)


if __name__ == "__main__":
    main()
