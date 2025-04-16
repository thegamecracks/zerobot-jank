#!/usr/bin/python3
import argparse
import getpass
import platform
import shutil
import string
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ALLOWED_ARCHITECTURES = ("armv7l", "aarch64")
ARCH = platform.machine()
if ARCH not in ALLOWED_ARCHITECTURES:
    sys.exit(f"System architecture is {ARCH}, must be one of armv7l, aarch64")

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

PROJECT_ROOT = Path(__file__).parent.resolve()
MEDIAMTX_SOURCES = {
    "armv7l": "https://github.com/bluenviron/mediamtx/releases/download/v1.12.0/mediamtx_v1.12.0_linux_armv7.tar.gz",
    "aarch64": "https://github.com/bluenviron/mediamtx/releases/download/v1.12.0/mediamtx_v1.12.0_linux_arm64v8.tar.gz",
}

apt_updated = False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print actions that would be taken",
    )
    parser.add_argument(
        "--force-mediamtx-arch",
        choices=ALLOWED_ARCHITECTURES,
        help="(Re)install mediamtx with the given architecture",
    )
    parser.add_argument(
        "--skip-camera",
        action="store_true",
        help="Continue when camera is undetected",
    )

    args = parser.parse_args()
    dry_run: bool = args.dry_run
    force_mediamtx_arch: str = args.force_mediamtx_arch
    skip_camera: bool = args.skip_camera

    check_camera(skip_camera=skip_camera)
    maybe_download_mediamtx(dry_run=dry_run, force_mediamtx_arch=force_mediamtx_arch)

    apt_cache = AptCache()
    apt_cache.open()

    maybe_install_nginx(apt_cache, dry_run=dry_run)
    copy_html_files(dry_run=dry_run)
    update_nginx_config(dry_run=dry_run)

    maybe_create_venv(apt_cache, dry_run=dry_run)

    update_mediamtx_service(dry_run=dry_run)
    update_controller_service(dry_run=dry_run)
    restart_services(dry_run=dry_run)


def check_camera(*, skip_camera: bool) -> None:
    output = check_output("rpicam-hello", "--list-cameras")
    if "No cameras available!" not in output:
        print("Raspberry Pi camera detected")
    elif skip_camera:
        print("Raspberry Pi camera not detected, ignoring.")
    else:
        sys.exit(
            "Raspberry Pi camera not detected, aborting.\n"
            "If you really want to continue setup, re-run this script "
            "with the --skip-camera flag."
        )


def maybe_download_mediamtx(
    *,
    dry_run: bool,
    force_mediamtx_arch: str | None = None,
) -> None:
    arch = force_mediamtx_arch or ARCH
    if Path("/usr/local/bin/mediamtx").is_file() and force_mediamtx_arch is None:
        return
    elif dry_run:
        return print(f"Would download mediamtx {arch} to /usr/local/bin/")

    print(f"Downloading mediamtx {arch}...")
    with tempfile.TemporaryFile("wb+") as f:
        with urllib.request.urlopen(MEDIAMTX_SOURCES[arch]) as response:
            shutil.copyfileobj(response, f)

        print("Extracting to /usr/local/bin/...")
        f.seek(0)
        with tarfile.open(fileobj=f, mode="r:gz") as archive:
            archive.extract("mediamtx", "/usr/local/bin")


def update_apt(apt_cache: AptCache, *, dry_run: bool) -> None:
    global apt_updated

    if apt_updated:
        return
    elif dry_run:
        print("Would update apt package index")
        apt_updated = True
    else:
        print("Updating apt package index...")
        apt_cache.update()
        apt_cache.open()
        apt_updated = True


def maybe_install_nginx(apt_cache: AptCache, *, dry_run: bool) -> None:
    nginx = apt_cache["nginx"]
    if nginx.is_installed:
        return

    update_apt(apt_cache, dry_run=dry_run)
    if dry_run:
        print("Would install nginx")
    else:
        print("Installing nginx...")
        nginx.mark_install()
        apt_cache.commit()


def copy_html_files(*, dry_run: bool) -> None:
    if dry_run:
        return print("Would copy HTML files to /var/www/html/")

    print("Copying HTML files to /var/www/html/")
    shutil.copytree(PROJECT_ROOT / "var/www/html/", "/var/www/html/", dirs_exist_ok=True)


def update_nginx_config(*, dry_run: bool) -> None:
    default = Path("/etc/nginx/sites-enabled/default")
    if not default.is_file():
        pass
    elif dry_run:
        print("Would remove default nginx site configuration")
    else:
        print("Removing default nginx site configuration...")
        default.unlink()

    src_sites = list(PROJECT_ROOT.joinpath("etc/nginx/sites-available").iterdir())
    dest_sites: list[Path] = [
        Path("/etc/nginx/sites-available") / path.name for path in src_sites
    ]

    if not src_sites:
        pass
    elif dry_run:
        print("Would copy nginx configuration to /etc/nginx/sites-available/")
        print("Would add symlinks to /etc/nginx/sites-enabled/")
        print("Would restart nginx")
    else:
        print("Copying nginx configuration to /etc/nginx/sites-available/...")
        for src, dest in zip(src_sites, dest_sites):
            shutil.copyfile(src, dest)

        print("Adding symlinks to /etc/nginx/sites-enabled/...")
        for dest in dest_sites:
            link = Path("/etc/nginx/sites-enabled").joinpath(dest.name)
            if link.resolve() == dest:
                continue

            link.symlink_to(dest)

        print("Restarting nginx...")
        check_call("systemctl", "restart", "nginx")


def maybe_create_venv(apt_cache: AptCache, *, dry_run: bool) -> None:
    venv = PROJECT_ROOT.joinpath(".venv")
    if venv.is_dir():
        return

    maybe_install_python_dev(apt_cache, dry_run=dry_run)

    if dry_run:
        return print("Would create controller.py virtual environment")

    print("Creating controller.py virtual environment...")
    check_call(sys.executable, "-m", "venv", venv)
    print("Installing controller.py dependencies...")
    check_call(venv / "bin/pip", "install", "-r", PROJECT_ROOT / "requirements.txt")


def maybe_install_python_dev(apt_cache: AptCache, *, dry_run: bool) -> None:
    dev = apt_cache["python3-dev"]
    if dev.is_installed:
        return

    update_apt(apt_cache, dry_run=dry_run)
    if dry_run:
        print("Would install python3-dev")
    else:
        print("Installing python3-dev...")
        dev.mark_install()
        apt_cache.commit()


def update_mediamtx_service(*, dry_run: bool) -> None:
    src = PROJECT_ROOT / "etc/systemd/system/zerobot-mediamtx.service"
    copy_service_file(src, dry_run=dry_run)


def update_controller_service(*, dry_run: bool) -> None:
    src = PROJECT_ROOT / "etc/systemd/system/zerobot-controller.service"
    copy_service_file(src, dry_run=dry_run)


def copy_service_file(src: Path, *, dry_run: bool) -> None:
    if dry_run:
        return print(f"Would copy {src.name} to /etc/systemd/system/")

    print(f"Copying {src.name} to /etc/systemd/system/...")
    dest = Path("/etc/systemd/system") / src.name
    content = src.read_text("utf8")
    content = replace_service_substitutions(content)
    dest.write_text(content, "utf8")


def replace_service_substitutions(content: str) -> str:
    return string.Template(content).substitute(
        {
            "PROJECT": PROJECT_ROOT,
            "PYTHON": PROJECT_ROOT / ".venv/bin/python",
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
