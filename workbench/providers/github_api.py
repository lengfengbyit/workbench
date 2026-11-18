"""Minimal GitHub GraphQL client (standard library only) and the query fragments the provider uses."""
import json
import os
import urllib.error
import urllib.request

from ..util import run
from .base import ProviderError

PROJECT_VALUES = """
projectItems(first: 5) { nodes { fieldValues(first: 30) { nodes {
  __typename
  ... on ProjectV2ItemFieldSingleSelectValue { name field { ... on ProjectV2FieldCommon { name } } }
  ... on ProjectV2ItemFieldDateValue { date field { ... on ProjectV2FieldCommon { name } } }
  ... on ProjectV2ItemFieldIterationValue { title startDate duration field { ... on ProjectV2FieldCommon { name } } }
} } } }
"""

ISSUE_FIELDS = """
number title state url createdAt updatedAt closedAt
repository { nameWithOwner }
labels(first: 20) { nodes { name } }
milestone { title dueOn }
parent { number title state url repository { nameWithOwner } }
""" + PROJECT_VALUES

PR_FIELDS = """
number title url state isDraft reviewDecision headRefName baseRefName
repository { nameWithOwner }
commits(last: 50) { nodes { commit { oid committedDate messageHeadline statusCheckRollup { state } } } }
"""

TIMELINE = """
timelineItems(first: 50, itemTypes: [CROSS_REFERENCED_EVENT, CONNECTED_EVENT]) { nodes {
  __typename
  ... on CrossReferencedEvent { source { __typename ... on PullRequest { %s } } }
  ... on ConnectedEvent { subject { __typename ... on PullRequest { %s } } }
} }
""" % (PR_FIELDS, PR_FIELDS)


class GraphQLClient:
    def __init__(self, url, token=None):
        self.url = url
        self._token = token

    @property
    def token(self):
        if not self._token:
            self._token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or self._from_gh()
        if not self._token:
            raise ProviderError("no GitHub token: set GITHUB_TOKEN, or log in with `gh auth login`")
        return self._token

    @staticmethod
    def _from_gh():
        code, out = run(["gh", "auth", "token"], timeout=20)
        return out if code == 0 and out else None

    def query(self, query, variables=None):
        """Run a query and return its `data`. Partial errors (for example a project the token cannot read) are tolerated
        when data came back; they are kept in self.errors for the doctor."""
        body = json.dumps({"query": query, "variables": variables or {}}).encode()
        req = urllib.request.Request(self.url, data=body, headers={
            "Authorization": f"Bearer {self.token}", "Content-Type": "application/json",
            "GraphQL-Features": "sub_issues", "User-Agent": "workbench"})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                payload = json.load(resp)
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:200]
            raise ProviderError(f"GitHub API returned HTTP {e.code}: {detail}") from e
        except urllib.error.URLError as e:
            raise ProviderError(f"cannot reach GitHub: {e.reason}") from e
        self.errors = payload.get("errors") or []
        if not payload.get("data"):
            raise ProviderError("GitHub API error: " + "; ".join(e.get("message", "?") for e in self.errors)[:300])
        return payload["data"]
