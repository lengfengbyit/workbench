# AGENTS.md: set up a workbench for the user

Follow this when the user asks you to set up, configure or repair their workbench. Ask only what you cannot find out.

## One-time setup

1. Prerequisites: `python3 --version` is 3.9 or newer, and `git --version` works.
2. Find out two things from the user (infer first, then confirm):
   - the directory that holds their git clones (`workspace`);
   - the tracker: `github`, or a plugin they already have (then you also need its module name and path).
3. For GitHub, check authentication: `GITHUB_TOKEN` / `GH_TOKEN` is set, or `gh auth status` succeeds. If not, tell
   the user to run `gh auth login` themselves. Never ask them to paste a token into the chat and never write one to
   a file. For Projects v2 data they also need `gh auth refresh -s read:project`.
4. Write the config and run the checks:
   `python3 -m workbench init --provider github --workspace <dir>`
   Add provider options with `--set github.search="-label:wontfix"`, `--set github.stages='["Todo","Doing","Done"]'`.
   Only issues in repositories cloned under the workspace are collected; `--set github.workspace_only=false` collects
   everything assigned to the user.
5. Read the `doctor` output. Fix every `fail` before continuing. A `warn` about the workspace having no repositories
   means the directory is wrong.
6. Collect once and look at the result: `python3 -m workbench collect`. Exit code 2 means some data could not be
   collected; the messages are in `data.json` under `collectionErrors`.
7. Start it: `./restart.sh` (background, `127.0.0.1:8765`). Always use this script to restart; do not start
   `python3 -m workbench serve` in a session shell, or you will leave extra processes behind.
8. Tell the user the URL. If you bound a host other than 127.0.0.1, say that the page has no login.

To see the UI without any account: `python3 -m workbench serve --demo`.

## Ongoing work

- Config and notes live in the data directory (`$WORKBENCH_HOME`, else `~/.config/workbench`), not in this repo.
  Edit `notes.json` in place; a refresh in the UI picks it up, no restart needed. Restart after changing `config.json`.
- When the user gives you a PRD or design doc for an item, read all of it, then fill `requirements.<id>.info`
  (summary, goals, `scope` with `ours: true` on the parts their team owns, milestones, risks) and add the link to
  `docs`. Mark parts you cannot attribute as "to be confirmed" in `desc` and ask. Format: `examples/notes.example.json`.
- To record how a requirement's repos call each other, fill `nodes` (in call order) and `edges`
  (`[caller, callee, description]`) from what the code shows, and ask when unsure.
- To archive a requirement, use the UI button or append `{"id": "...", "title": "...", "date": "YYYY-MM-DD"}` to
  `archived`. Confirm with the user first.

## Rules

- The workbench never changes the user's repositories. Do not add commands that checkout, pull, stash or reset.
- Do not copy tokens, passwords or internal hostnames into files, logs or replies. Name the file and the key only.
- Adding a tracker means adding a provider (`workbench/providers/base.py` describes the contract). Do not branch on
  tracker names in the core.
- Run `python3 -m unittest discover -s tests -t .` after changing Python code, and
  `node tests/ui_smoke.js <data.json>` after changing anything under `workbench/static/`.
