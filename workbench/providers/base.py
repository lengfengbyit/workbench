"""The contract between the core and a task tracker.

A provider turns a tracker (GitHub, a company issue system, ...) into the plain dicts below. The core never
touches tracker-specific fields. Ids are strings. Dates are 'YYYY-MM-DD'. Timestamps are epoch milliseconds.

Item (what list_items / list_online_items return)
    id, title, status, type          status must be one of workflow()["stages"] names
    parent          id of the parent item (an epic / feature), or None
    num             int used only for ordering, larger = newer
    plan            iteration / milestone label (optional)
    iteration       [start, end] dates (optional; otherwise parse_iteration(plan, year) is tried)
    qa, rd, pd      optional free text shown in the story table
    devStart, devEnd, testPlan, release, testStart, testEnd   optional dates
    created, modified

Parent (get_parent): id, title, status, type, plan, actualRelease, modified, detailText, docs
    docs: [{"type": "tracker", "title", "url", "source": "tracker"}]

Dev info (dev_info): {item id: {"commits": [Commit], "crs": [Review]}}
    Commit: repo, branch, sha, ts, msg, pipeline ("PASS" / "FAIL" / None), pipelineUrl, changeUrl,
            merged (optional True when the tracker knows it reached the trunk, e.g. squash merges)
    Review: repo, branch, status, msg, url
"""

DEFAULT_STAGE_COLORS = ["#94a3b8", "#3b82f6", "#6366f1", "#a855f7", "#f59e0b", "#14b8a6", "#0ea5e9", "#10b981"]


class ProviderError(RuntimeError):
    """Raised for tracker problems that should be shown to the user (auth, network, bad config)."""


class Provider:
    name = "provider"
    id_prefix = ""       # shown before every id in the UI, e.g. "PROJ-"

    def __init__(self, config):
        self.config = config
        self.options = config.get(self.name) or {}

    # ---- required ----
    def workflow(self):
        """{"stages": [{"name", "color", "offPath"?}], "done": [names], "online": [names], "dev": [names]}

        offPath marks a stage outside the normal progression (paused, blocked). It is left off the progress line
        and should get a warning colour. Use red only for stages that mean something is wrong.

        done: items the tracker no longer lists as in progress. online: shipped. dev: still being developed
        (used for the overdue-test-date alert)."""
        raise NotImplementedError

    def whoami(self):
        raise NotImplementedError

    def list_items(self):
        """Open items assigned to the current user."""
        raise NotImplementedError

    def get_parent(self, item_id):
        raise NotImplementedError

    def dev_info(self, ids):
        raise NotImplementedError

    # ---- optional ----
    def scope(self):
        """Extra label shown next to the user, e.g. a project or organisation."""
        return ""

    def local_repos(self):
        """{repo name as used in commits: path of the local clone} for clones the tracker can recognise. These repos are
        listed with their branches and local state even when no item refers to them. Empty when unsupported."""
        return {}

    def list_online_items(self, days):
        """Items assigned to the user that were shipped within `days` days. Empty when unsupported."""
        return []

    def item_url(self, item_id):
        return ""

    def links(self):
        """URL templates for repo and branch pages. {repo}, {branch} and {branch2} (double-encoded) are filled in."""
        return {"repo": "", "branch": ""}

    def refs_in_message(self, message, repo):
        """Ids of items a commit message refers to. Used to tell one item's commits from other items' on a branch."""
        return set()

    def parse_iteration(self, plan, year):
        """[start, end] for an iteration label, or None."""
        return None

    def doctor(self):
        """[(level, text)] with level in ok / warn / fail. Check credentials, tools and permissions here."""
        return []
