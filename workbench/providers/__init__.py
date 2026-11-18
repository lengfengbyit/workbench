"""Provider registry. Built-ins live here; anything else is a plugin loaded from config.

config.json:
    "provider": "github"                      built-in name, or the name a plugin registers
    "provider_module": "my_pkg"               optional: import this module and use its `Provider` class
    "plugin_paths": ["~/code/my-plugin"]      optional: extra directories to put on sys.path first
Plugins can also register an entry point in the group "workbench.providers".
"""
import importlib
import os
import sys

from .base import Provider, ProviderError

BUILTIN = {
    "github": ("workbench.providers.github", "GitHubProvider"),
    "demo": ("workbench.providers.demo", "DemoProvider"),
}


def _entry_points():
    from importlib import metadata
    eps = metadata.entry_points()
    return eps.select(group="workbench.providers") if hasattr(eps, "select") else eps.get("workbench.providers", [])


def load_provider(config):
    for path in [*config.get("plugin_paths", []), *filter(None, os.environ.get("WORKBENCH_PLUGIN_PATH", "").split(os.pathsep))]:
        path = os.path.abspath(os.path.expanduser(path))
        if path not in sys.path:
            sys.path.insert(0, path)
    name = config.get("provider")
    if not name and not config.get("provider_module"):
        raise ProviderError(
            "no provider configured. Create config.json in the data directory ($WORKBENCH_HOME, default "
            "~/.config/workbench) with `python3 -m workbench init --provider github --workspace <dir>`, "
            "or try the UI without an account: `python3 -m workbench serve --demo`")
    if config.get("provider_module"):
        cls = getattr(importlib.import_module(config["provider_module"]), "Provider")
    elif name in BUILTIN:
        module, attr = BUILTIN[name]
        cls = getattr(importlib.import_module(module), attr)
    else:
        found = [ep for ep in _entry_points() if ep.name == name]
        if not found:
            raise ProviderError(f"unknown provider {name!r}: set \"provider\" in config.json to one of "
                                f"{sorted(BUILTIN)}, or point \"provider_module\" at a plugin "
                                f"(and \"plugin_paths\" at the directory that contains it)")
        cls = found[0].load()
    return cls(config)


__all__ = ["Provider", "ProviderError", "load_provider", "BUILTIN"]
