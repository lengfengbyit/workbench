"""Command line: serve, collect, init, doctor."""
import argparse
import os
import sys
import tempfile

from . import __version__
from .app import App, serve
from .providers import ProviderError, load_provider
from .repos import find_repos
from .settings import Settings
from .util import run


def doctor(settings, provider=None):
    """Print checks and return the number of failures."""
    fails = 0

    def report(level, text):
        nonlocal fails
        fails += level == "fail"
        print(f"[{level:>4}] {text}")

    report("ok" if sys.version_info >= (3, 9) else "fail", f"python {sys.version.split()[0]} (needs 3.9+)")
    code, out = run(["git", "--version"])
    report("ok" if code == 0 else "fail", out if code == 0 else "git not found on PATH")
    ws = settings.workspace
    if os.path.isdir(ws):
        repos = find_repos(ws)
        report("ok" if repos else "warn", f"workspace {ws}: {len(repos)} git repo(s) found" +
               ("" if repos else " (set \"workspace\" in config.json to the directory that holds your clones)"))
    else:
        report("fail", f"workspace {ws} does not exist")
    report("ok" if os.path.exists(settings.config_path) else "warn",
           f"config {settings.config_path}" + ("" if os.path.exists(settings.config_path) else " not found, run `workbench init`"))
    try:
        provider = provider or load_provider(settings.config)
    except ProviderError as e:
        report("fail", str(e))
        return fails
    except Exception as e:  # noqa: BLE001  plugin import errors
        report("fail", f"cannot load provider {settings.config.get('provider')!r}: {e}")
        return fails
    report("ok", f"provider {provider.name}")
    try:
        for level, text in provider.doctor():
            report(level, text)
    except Exception as e:  # noqa: BLE001
        report("fail", f"provider check crashed: {e}")
    return fails


def _set_dotted(config, key, value):
    parts = key.split(".")
    node = config
    for p in parts[:-1]:
        node = node.setdefault(p, {})
    try:
        import json
        node[parts[-1]] = json.loads(value)
    except ValueError:
        node[parts[-1]] = value


def cmd_init(args):
    settings = Settings(args.home)
    config = dict(settings._read())
    if args.provider:
        config["provider"] = args.provider
    if args.workspace:
        config["workspace"] = os.path.abspath(os.path.expanduser(args.workspace))
    for item in args.set or []:
        key, _, value = item.partition("=")
        _set_dotted(config, key, value)
    config.setdefault("provider", "github")
    settings.save_config(config)
    print(f"wrote {settings.config_path}")
    return 1 if doctor(Settings(args.home)) else 0


def demo_app():
    from .providers.demo import DemoProvider, make_workspace
    root = tempfile.mkdtemp(prefix="workbench-demo-")
    commits = make_workspace(root)
    settings = Settings(os.path.join(root, "_home"), {"provider": "demo", "workspace": root})
    print(f"demo workspace: {root}")
    return App(settings, DemoProvider(settings.config, commits))


def cmd_serve(args):
    app = demo_app() if args.demo else App(Settings(args.home))
    cfg = app.settings.config
    serve(app, args.host or cfg["host"], args.port or int(cfg["port"]))
    return 0


def cmd_collect(args):
    app = demo_app() if args.demo else App(Settings(args.home))
    data = app.refresh(fetch=not args.no_fetch)
    print(f"{len(data['requirements'])} requirements, {len(data['alerts'])} alerts, written to {app.settings.cache_path}")
    return 0 if data["collectionOk"] else 2


def cmd_doctor(args):
    return 1 if doctor(Settings(args.home)) else 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="workbench", description="Local dashboard for your work items and the code behind them.")
    ap.add_argument("--version", action="version", version=__version__)
    ap.add_argument("--home", help="data directory (default: $WORKBENCH_HOME or ~/.config/workbench)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("serve", help="start the web UI")
    p.add_argument("--host")
    p.add_argument("--port", type=int)
    p.add_argument("--demo", action="store_true", help="fictional data in throw-away repos, no account needed")
    p.set_defaults(fn=cmd_serve)
    p = sub.add_parser("collect", help="collect once, write data.json and exit")
    p.add_argument("--no-fetch", action="store_true", help="skip git fetch")
    p.add_argument("--demo", action="store_true")
    p.set_defaults(fn=cmd_collect)
    p = sub.add_parser("init", help="write config.json and run the checks")
    p.add_argument("--provider", help="github, demo, or the name a plugin registers")
    p.add_argument("--workspace", help="directory that holds your git clones")
    p.add_argument("--set", action="append", metavar="KEY=VALUE", help="extra config, dotted keys, JSON values (repeatable)")
    p.set_defaults(fn=cmd_init)
    p = sub.add_parser("doctor", help="check tools, credentials and config")
    p.set_defaults(fn=cmd_doctor)
    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except ProviderError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
