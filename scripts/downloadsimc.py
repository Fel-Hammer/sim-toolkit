import os
import sys
import re
import requests
from bs4 import BeautifulSoup
import py7zr
import subprocess
import platform
from datetime import datetime
from urllib.parse import urljoin


def remove_if_exists(file_path):
    if os.path.exists(file_path):
        print(f"Removing existing file: {file_path}")
        os.remove(file_path)


def get_latest_version_url(base_url):
    response = requests.get(base_url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    rows = soup.find_all("tr")

    system = platform.system().lower()
    arch = platform.machine().lower()

    if system == "darwin":
        pattern = re.compile(r"simc-.*-macos-.*\.dmg")
    elif system == "windows":
        pattern = (
            re.compile(r"simc-.*-win64\.7z")
            if "arm" not in arch
            else re.compile(r"simc-.*-winarm64\.7z")
        )
    else:
        raise ValueError(f"Unsupported system: {system}")

    valid_files = [
        (
            datetime.strptime(row.find_all("td")[2].text.strip(), "%Y-%m-%d %H:%M"),
            row.find("a")["href"],
        )
        for row in rows
        if row.find("a") and pattern.match(row.find("a").text)
    ]

    if not valid_files:
        raise ValueError("No matching SimulationCraft versions found")

    return urljoin(base_url, max(valid_files, key=lambda x: x[0])[1])


def download_file(url, filename):
    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        total_size = int(r.headers.get("content-length", 0))
        block_size = 8192
        downloaded = 0
        print(f"Downloading {filename}")
        with open(filename, "wb") as f:
            for chunk in r.iter_content(chunk_size=block_size):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    progress = int(50 * downloaded / total_size)
                    sys.stdout.write(
                        f"\r[{'=' * progress}{' ' * (50 - progress)}] {downloaded}/{total_size} bytes"
                    )
                    sys.stdout.flush()
    print()  # New line after the progress bar


def extract_simc(filename):
    print(f"Extracting {filename}")
    if filename.endswith(".7z"):
        with py7zr.SevenZipFile(filename, mode="r") as z:
            z.extract(path="temp", targets=["simc.exe"])
        os.rename("temp/simc.exe", "simc.exe")
        os.rmdir("temp")
        return os.path.abspath("simc.exe")
    elif filename.endswith(".dmg"):
        try:
            result = subprocess.run(
                ["hdiutil", "attach", filename],
                capture_output=True,
                text=True,
                check=True,
            )
            mount_point = next(
                (
                    line.split("/Volumes/")[-1].strip()
                    for line in result.stdout.split("\n")
                    if "/Volumes/" in line
                ),
                None,
            )
            if not mount_point:
                raise ValueError("Could not find mount point for DMG")
            mount_point = f"/Volumes/{mount_point}"

            simc_path = None
            for root, _, files in os.walk(mount_point):
                if "simc" in files:
                    simc_path = os.path.join(root, "simc")
                    break

            if not simc_path:
                raise ValueError(
                    f"Could not find simc executable in DMG at {mount_point}"
                )

            subprocess.run(["cp", simc_path, "."], check=True)
            return os.path.abspath("simc")
        finally:
            if mount_point:
                subprocess.run(["hdiutil", "detach", mount_point], check=True)


def download_and_extract_simc():
    base_url = "http://downloads.simulationcraft.org/nightly/"
    print("Fetching latest SimulationCraft version...")
    latest_url = get_latest_version_url(base_url)
    filename = os.path.basename(latest_url)

    # Check and remove existing simc executable
    simc_executable = "simc.exe" if platform.system().lower() == "windows" else "simc"
    remove_if_exists(simc_executable)

    # Check and remove existing downloaded file
    remove_if_exists(filename)

    download_file(latest_url, filename)
    simc_path = extract_simc(filename)
    os.remove(filename)

    return simc_path


if __name__ == "__main__":
    try:
        simc_executable_path = download_and_extract_simc()
        print(
            f"SimulationCraft CLI downloaded and extracted to: {simc_executable_path}"
        )
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)
