"""Port discovery and management for the local implementer agent server."""

from pathlib import Path
import socket
from typing import Optional
import httpx

START_PORT = 8090
END_PORT = 8099
DEFAULT_HOST = "127.0.0.1"


def get_cache_file() -> Path:
    # Look for .scratch in repo root, fallback to /tmp
    repo_root = Path(__file__).resolve().parent.parent.parent
    scratch_dir = repo_root / ".scratch"
    if not scratch_dir.exists():
        try:
            scratch_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            scratch_dir = Path("/tmp")
    return scratch_dir / "implementer_port.txt"


def read_cached_port() -> Optional[int]:
    cache_file = get_cache_file()
    if cache_file.exists():
        try:
            port = int(cache_file.read_text(encoding="utf-8").strip())
            if START_PORT <= port <= END_PORT:
                return port
        except (ValueError, OSError):
            pass
    return None


def save_cached_port(port: int) -> None:
    cache_file = get_cache_file()
    try:
        cache_file.write_text(str(port), encoding="utf-8")
    except OSError:
        pass


def is_port_free(port: int, host: str = DEFAULT_HOST) -> bool:
    """Checks if a TCP port is free to bind."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


async def is_implementer_active(port: int, host: str = DEFAULT_HOST) -> bool:
    """Checks if an implementer server is responding on the given port."""
    url = f"http://{host}:{port}/healthz"
    try:
        async with httpx.AsyncClient(timeout=1.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("agent") == "implementer_agent" or data.get("status") == "ok"
    except Exception:
        pass
    return False


async def find_active_server(
    start_port: int = START_PORT,
    end_port: int = END_PORT,
    host: str = DEFAULT_HOST,
) -> Optional[int]:
    """Scans for a currently running implementer agent server."""
    cached = read_cached_port()
    if cached and await is_implementer_active(cached, host):
        return cached

    for port in range(start_port, end_port + 1):
        if port == cached:
            continue
        if await is_implementer_active(port, host):
            save_cached_port(port)
            return port

    return None


def find_free_port(
    start_port: int = START_PORT,
    end_port: int = END_PORT,
    host: str = DEFAULT_HOST,
) -> int:
    """Finds an unused port in the specified range, prioritizing the cached port."""
    cached = read_cached_port()
    if cached and is_port_free(cached, host):
        return cached

    for port in range(start_port, end_port + 1):
        if is_port_free(port, host):
            save_cached_port(port)
            return port

    raise RuntimeError(
        f"No free ports found in range {start_port}-{end_port} on host {host}."
    )
