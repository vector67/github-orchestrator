import subprocess

KEYCHAIN_SERVICE = "harvest-api"


def keychain_token() -> str:
    return subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
                          capture_output=True, text=True, check=True).stdout.strip()
