from __future__ import annotations

import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse, urlunparse

_TRYCLOUDFLARE_URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com", re.IGNORECASE)


@dataclass
class QuickTunnelHandle:
    process: subprocess.Popen[bytes]
    public_base_url: str
    log_path: Path

    def stop(self) -> None:
        if self.process.poll() is not None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=3)


def normalize_public_base_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("public_base_url must use http:// or https://")
    if not parsed.netloc:
        raise ValueError("public_base_url must include a host")

    normalized_path = parsed.path.rstrip("/")
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            normalized_path,
            "",
            "",
            "",
        )
    )


def start_cloudflared_quick_tunnel(
    *,
    local_url: str,
    output_dir: Path,
    cloudflared_bin: str = "cloudflared",
    timeout_seconds: float = 30.0,
) -> QuickTunnelHandle:
    if shutil.which(cloudflared_bin) is None:
        raise RuntimeError(f"{cloudflared_bin!r} not found in PATH. Install cloudflared first.")

    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "cloudflared_tunnel.log"

    with log_path.open("w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            [cloudflared_bin, "tunnel", "--url", local_url],
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )

    deadline = time.monotonic() + timeout_seconds
    discovered_url: str | None = None
    latest_logs = ""

    while time.monotonic() < deadline:
        latest_logs = log_path.read_text(encoding="utf-8", errors="replace")
        match = _TRYCLOUDFLARE_URL_RE.search(latest_logs)
        if match:
            discovered_url = normalize_public_base_url(match.group(0))
            break

        if process.poll() is not None:
            break

        time.sleep(0.25)

    if discovered_url is None:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)

        tail_lines = "\n".join(latest_logs.strip().splitlines()[-20:])
        details = f"\ncloudflared log tail:\n{tail_lines}" if tail_lines else ""
        raise RuntimeError(
            f"Failed to establish cloudflared quick tunnel within {timeout_seconds:.0f}s.{details}"
        )

    return QuickTunnelHandle(
        process=process,
        public_base_url=discovered_url,
        log_path=log_path,
    )
