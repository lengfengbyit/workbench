"""Small helpers shared by the core and the providers: subprocess, git, date parsing."""
import re
import subprocess
from datetime import datetime


def run(args, cwd=None, timeout=180, env=None):
    """Run a command and return (exit code, output). stderr is only included on failure."""
    try:
        p = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env)
    except FileNotFoundError:
        return 127, f"command not found: {args[0]}"
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout}s: {' '.join(map(str, args[:3]))}"
    return p.returncode, (p.stdout if p.returncode == 0 else p.stdout + p.stderr).strip()


def git(repo, *args):
    """Run `git -C repo ...`; return stdout, or None when git exits non-zero."""
    code, out = run(["git", "-C", repo, *args], timeout=120)
    return out if code == 0 else None


def iso_date(value):
    """Return YYYY-MM-DD for ISO-like strings ('2026-10-23', '2026-10-23T08:00:00Z', '2026-10-23 00:00:00.0')."""
    if not value:
        return None
    m = re.match(r"(\d{4}-\d{2}-\d{2})", str(value))
    return m.group(1) if m else None


def epoch_ms(value):
    """Milliseconds since the epoch for an ISO-8601 timestamp such as '2026-10-23T08:00:00Z'; None if unparsable."""
    if not value:
        return None
    try:
        return int(datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp() * 1000)
    except ValueError:
        return None
