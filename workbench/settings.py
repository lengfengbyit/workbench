"""Where config and data live, and how config is read.

Everything user-specific (config.json, notes.json, the data cache, pid and logs) lives in the data
directory, never next to the code: $WORKBENCH_HOME, else $XDG_CONFIG_HOME/workbench, else ~/.config/workbench.
"""
import json
import os
import re

DEFAULTS = {"host": "127.0.0.1", "port": 8765}

# Options the page may change: key -> (min, max, default). Everything else in config.json stays hand-edited.
UI_OPTIONS = {"recent_branch_days": (1, 90, 7)}


def ui_config(config):
    """Current values of UI_OPTIONS, falling back to the default when config.json holds something unusable."""
    out = {}
    for key, (lo, hi, default) in UI_OPTIONS.items():
        value = config.get(key, default)
        out[key] = value if isinstance(value, int) and not isinstance(value, bool) and lo <= value <= hi else default
    return out


def validate_ui_config(body):
    """The UI_OPTIONS entries of a request body, checked. Raises ValueError with a message for the page."""
    changes = {}
    for key, value in (body or {}).items():
        if key not in UI_OPTIONS:
            raise ValueError(f"不支持在页面上修改 {key}")
        lo, hi, _ = UI_OPTIONS[key]
        if isinstance(value, bool) or not re.fullmatch(r"\d+", str(value).strip()):
            raise ValueError(f"{key} 需要是整数")
        number = int(str(value).strip())
        if not lo <= number <= hi:
            raise ValueError(f"{key} 需要在 {lo} 到 {hi} 之间")
        changes[key] = number
    return changes


def default_home():
    if os.environ.get("WORKBENCH_HOME"):
        return os.path.expanduser(os.environ["WORKBENCH_HOME"])
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "workbench")


def resolve_workspace(config):
    """Root directory that contains the git clones. Falls back to the current directory."""
    path = os.environ.get("WORKBENCH_WORKSPACE") or config.get("workspace") or os.getcwd()
    return os.path.abspath(os.path.expanduser(path))


class Settings:
    """Paths and config for one workbench instance. Tests and --demo build their own with a temp home."""

    def __init__(self, home=None, overrides=None):
        self.home = os.path.abspath(os.path.expanduser(home)) if home else default_home()
        self.config_path = os.path.join(self.home, "config.json")
        self.notes_path = os.path.join(self.home, "notes.json")
        self.cache_path = os.path.join(self.home, "data.json")
        self.pid_path = os.path.join(self.home, "app.pid")
        self.log_dir = os.path.join(self.home, "logs")
        self.config = {**DEFAULTS, **self._read(), **(overrides or {})}

    def _read(self):
        if not os.path.exists(self.config_path):
            return {}
        try:
            with open(self.config_path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            raise SystemExit(f"cannot read {self.config_path}: {e}")
        return data if isinstance(data, dict) else {}

    @property
    def workspace(self):
        return resolve_workspace(self.config)

    def update_config(self, changes):
        """Write `changes` into config.json, keeping every other key the file has, and use them from now on."""
        self.save_config({**self._read(), **changes})
        self.config = {**self.config, **changes}

    def save_config(self, data):
        os.makedirs(self.home, exist_ok=True)
        tmp = self.config_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.config_path)
