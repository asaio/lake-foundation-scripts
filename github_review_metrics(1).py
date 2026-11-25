#!/usr/bin/env python3
"""Quarterly GitHub review dataset and annual summary.

Outputs beside this script:
  github_metrics_<user>_<YYYYQn>.json              quarterly summary/cache
  github_metrics_<user>_<year>_annual.json         annual summary
  github_metrics_<user>_<YYYYQn>_data/             flat NDJSON analytical tables
  github_metrics_<user>_<YYYYQn>_graphql.jsonl     every GraphQL response received

The flat *.jsonl tables are intended for Polars scan_ndjson() and DuckDB
read_json(..., format='newline_delimited'). Existing quarterly summaries are
used as cache markers unless --overwrite is passed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

import requests

API_URL = "https://api.github.com/graphql"
TIMEOUT = 60
AGENTS = (
    "dependabot[bot]", "renovate[bot]", "github-actions[bot]",
    "copilot-swe-agent", "copilot-agent", "cursor-agent",
    "claude-code-bot", "coderabbitai[bot]",
)
TICKET_RE = re.compile(r"^\s*\[([^\]]+)\]")
VALID_TICKET_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*-\d+$")


def now() -> datetime:
    return datetime.now(timezone.utc)


def percentage(a: int, b: int) -> Optional[float]:
    return round(a * 100.0 / b, 2) if b else None


def normalize(values: Iterable[str]) -> set[str]:
    return {v.strip().casefold() for v in values if v.strip()}


def safe(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())


def current_quarter(day: date) -> int:
    return (day.month - 1) // 3 + 1


def quarter_dates(year: int, quarter: int) -> tuple[date, date]:
    starts = {1: (1, 1), 2: (4, 1), 3: (7, 1), 4: (10, 1)}
    ends = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}
    sm, sd = starts[quarter]
    em, ed = ends[quarter]
    return date(year, sm, sd), date(year, em, ed)


def write_json(path: Path, obj: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    tmp.replace(path)


def read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        value = json.load(f)
    if not isinstance(value, dict):
        raise ValueError("cached report is not an object")
    return value


def append_jsonl(path: Path, obj: Any) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n")


def extract_jira_ids(body: Optional[str]) -> list[str]:
    """Extract comma-separated JIRA-like IDs from the leading [bracket]."""
    match = TICKET_RE.match(body or "")
    if not match:
        return []
    values = [part.strip().upper() for part in match.group(1).split(",")]
    return list(dict.fromkeys(v for v in values if VALID_TICKET_RE.fullmatch(v)))


def gitflow_type(base: str, head: str) -> str:
    """Classify common Gitflow paths without assuming they enforce policy."""
    base_l, head_l = base.casefold(), head.casefold()
    if base_l in {"main", "master"}:
        if head_l == "develop": return "release_develop_to_main"
        if head_l.startswith("release/"): return "release_to_main"
        if head_l.startswith("hotfix/"): return "hotfix_to_main"
        return "direct_to_main"
    if base_l == "develop":
        if head_l.startswith("feature/"): return "feature_to_develop"
        if head_l.startswith("bugfix/"): return "bugfix_to_develop"
        if head_l.startswith("hotfix/"): return "hotfix_backmerge_to_develop"
        return "other_to_develop"
    if base_l.startswith("release/"): return "change_to_release"
    return "other"


@dataclass(frozen=True)
class Window:
    year: int
    quarter: int
    start: date
    calendar_end: date
    effective_end: date

    @property
    def label(self) -> str: return f"{self.year}Q{self.quarter}"


class GraphQL:
    def __init__(self, token: str, raw_path: Path, timeout: int = TIMEOUT) -> None:
        self.raw_path = raw_path
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "github-quarterly-review-dataset/3.0",
            "X-GitHub-Api-Version": "2022-11-28",
        })

    def call(self, operation: str, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        request_id = hashlib.sha256(
            (operation + json.dumps(variables, sort_keys=True)).encode()
        ).hexdigest()[:20]
        last: Optional[Exception] = None
        for attempt in range(5):
            started = now()
            try:
                r = self.session.post(
                    API_URL, json={"query": query, "variables": variables},
                    timeout=self.timeout,
                )
                payload = r.json()
                append_jsonl(self.raw_path, {
                    "request_id": request_id,
                    "operation": operation,
                    "fetched_at": started.isoformat(),
                    "http_status": r.status_code,
                    "variables": variables,
                    "response": payload,
                })
                if r.status_code in {429, 502, 503, 504}:
                    raise requests.HTTPError(f"temporary HTTP {r.status_code}")
                r.raise_for_status()
                if payload.get("errors"):
                    raise RuntimeError(json.dumps(payload["errors"], ensure_ascii=False))
                return payload["data"]
            except (requests.RequestException, ValueError, RuntimeError) as exc:
                last = exc
                if attempt == 4: break
                time.sleep(min(2 ** attempt, 16))
        raise RuntimeError(f"GraphQL operation {operation} failed: {last}") from last


class Dataset:
    SEARCH = """
    query SearchPRs($query:String!,$cursor:String){
      search(type:ISSUE,query:$query,first:100,after:$cursor){
        issueCount nodes{... on PullRequest{
          id databaseId number url title body createdAt updatedAt closedAt mergedAt
          merged state isDraft additions deletions changedFiles baseRefName headRefName
          author{login} mergedBy{login} repository{id nameWithOwner isPrivate}
        }} pageInfo{hasNextPage endCursor}
      } rateLimit{cost remaining resetAt}
    }"""
    CONNECTIONS = {
        "issue_comments": """query PRComments($id:ID!,$cursor:String){node(id:$id){... on PullRequest{comments(first:100,after:$cursor){nodes{id databaseId url body createdAt updatedAt author{login}}pageInfo{hasNextPage endCursor}}}}}""",
        "reviews": """query PRReviews($id:ID!,$cursor:String){node(id:$id){... on PullRequest{reviews(first:100,after:$cursor){nodes{id databaseId url body state submittedAt createdAt updatedAt author{login} commit{oid}}pageInfo{hasNextPage endCursor}}}}}""",
        "threads": """query PRThreads($id:ID!,$cursor:String){node(id:$id){... on PullRequest{reviewThreads(first:100,after:$cursor){nodes{id isResolved isOutdated resolvedBy{login} path line startLine diffSide comments(first:100){nodes{id databaseId url body createdAt updatedAt state author{login} replyTo{id}}pageInfo{hasNextPage endCursor}}}pageInfo{hasNextPage endCursor}}}}}""",
        "commits": """query PRCommits($id:ID!,$cursor:String){node(id:$id){... on PullRequest{commits(first:100,after:$cursor){nodes{commit{oid url message headline authoredDate committedDate additions deletions changedFiles author{name email user{login}}committer{name email user{login}}}}pageInfo{hasNextPage endCursor}}}}}""",
    }
    THREAD_COMMENTS = """query ThreadComments($id:ID!,$cursor:String){node(id:$id){... on PullRequestReviewThread{comments(first:100,after:$cursor){nodes{id databaseId url body createdAt updatedAt state author{login} replyTo{id}}pageInfo{hasNextPage endCursor}}}}}"""

    def __init__(self, api: GraphQL, root: Path, username: str,
                 ignored: set[str], tracked: Optional[str], agents: set[str]) -> None:
        self.api, self.root, self.username = api, root, username
        self.ignored, self.tracked, self.agents = ignored, tracked, agents
        root.mkdir(parents=True, exist_ok=True)
        self.files = {name: root / f"{name}.jsonl" for name in (
            "pull_requests", "issue_comments", "review_threads",
            "review_comments", "reviews", "commits", "failures")}

    def all_pages(self, operation: str, query: str, pr_id: str,
                  connection: str) -> list[dict[str, Any]]:
        cursor, rows = None, []
        while True:
            data = self.api.call(operation, query, {"id": pr_id, "cursor": cursor})
            node = data.get("node")
            if not node: raise RuntimeError("GraphQL node unavailable")
            conn = node[connection]
            rows.extend(x for x in conn["nodes"] if x)
            if not conn["pageInfo"]["hasNextPage"]: return rows
            cursor = conn["pageInfo"]["endCursor"]

    def thread_comments(self, thread: dict[str, Any]) -> list[dict[str, Any]]:
        initial = thread.pop("comments")
        rows = [x for x in initial["nodes"] if x]
        cursor = initial["pageInfo"]["endCursor"]
        while initial["pageInfo"]["hasNextPage"]:
            data = self.api.call("ThreadComments", self.THREAD_COMMENTS,
                                 {"id": thread["id"], "cursor": cursor})
            initial = data["node"]["comments"]
            rows.extend(x for x in initial["nodes"] if x)
            cursor = initial["pageInfo"]["endCursor"]
        return rows

    def find_prs(self, w: Window) -> tuple[list[dict[str, Any]], int]:
        q = f"author:{self.username} is:pr created:{w.start}..{w.effective_end} sort:created-asc"
        cursor, rows, total = None, [], 0
        while True:
            data = self.api.call("SearchPRs", self.SEARCH, {"query": q, "cursor": cursor})
            conn, total = data["search"], data["search"]["issueCount"]
            rows.extend(x for x in conn["nodes"] if x)
            if not conn["pageInfo"]["hasNextPage"]: break
            cursor = conn["pageInfo"]["endCursor"]
        if total > 1000:
            raise RuntimeError(f"{w.label} has {total} PRs; GitHub search exposes at most 1,000")
        return rows, total

    def collect(self, w: Window) -> dict[str, Any]:
        prs, search_total = self.find_prs(w)
        totals: Counter[str] = Counter()
        reviewers: Counter[str] = Counter()
        agents: Counter[str] = Counter()
        totals["prs"] = len(prs)

        for idx, pr in enumerate(prs, 1):
            print(f"[{w.label} {idx}/{len(prs)}] {pr['repository']['nameWithOwner']}#{pr['number']}", file=sys.stderr)
            try:
                repo = pr["repository"]["nameWithOwner"]
                common = {"quarter": w.label, "pr_id": pr["id"], "repo": repo, "pr_number": pr["number"]}
                jira = extract_jira_ids(pr.get("body")) if pr["merged"] and pr["baseRefName"].casefold() in {"main", "master"} else []
                pr_row = {
                    **common, "database_id": pr.get("databaseId"), "url": pr["url"],
                    "title": pr["title"], "body": pr.get("body"),
                    "author_login": (pr.get("author") or {}).get("login"),
                    "merged_by_login": (pr.get("mergedBy") or {}).get("login"),
                    "created_at": pr["createdAt"], "updated_at": pr["updatedAt"],
                    "closed_at": pr.get("closedAt"), "merged_at": pr.get("mergedAt"),
                    "state": pr["state"], "merged": pr["merged"], "is_draft": pr["isDraft"],
                    "base_ref": pr["baseRefName"], "head_ref": pr["headRefName"],
                    "gitflow_type": gitflow_type(pr["baseRefName"], pr["headRefName"]),
                    "merged_to_main": bool(pr["merged"] and pr["baseRefName"].casefold() in {"main", "master"}),
                    "jira_ticket_ids": jira, "jira_ticket_count": len(jira),
                    "additions": pr["additions"], "deletions": pr["deletions"],
                    "changed_files": pr["changedFiles"], "repository_private": pr["repository"]["isPrivate"],
                }
                append_jsonl(self.files["pull_requests"], pr_row)
                totals["merged_prs"] += int(pr["merged"])
                totals["merged_to_main"] += int(pr_row["merged_to_main"])
                totals["prs_with_jira"] += int(bool(jira))

                issue_comments = self.all_pages("PRComments", self.CONNECTIONS["issue_comments"], pr["id"], "comments")
                reviews = self.all_pages("PRReviews", self.CONNECTIONS["reviews"], pr["id"], "reviews")
                threads = self.all_pages("PRThreads", self.CONNECTIONS["threads"], pr["id"], "reviewThreads")
                commits = self.all_pages("PRCommits", self.CONNECTIONS["commits"], pr["id"], "commits")

                for c in issue_comments:
                    append_jsonl(self.files["issue_comments"], {**common, "comment_id": c["id"], "database_id": c.get("databaseId"), "url": c["url"], "author_login": (c.get("author") or {}).get("login"), "body": c.get("body"), "created_at": c["createdAt"], "updated_at": c["updatedAt"]})
                change_at, approvals = None, []
                for r in reviews:
                    login = (r.get("author") or {}).get("login")
                    append_jsonl(self.files["reviews"], {**common, "review_id": r["id"], "database_id": r.get("databaseId"), "url": r["url"], "author_login": login, "state": r["state"], "body": r.get("body"), "submitted_at": r.get("submittedAt"), "created_at": r["createdAt"], "updated_at": r["updatedAt"], "commit_oid": (r.get("commit") or {}).get("oid")})
                    if (login or "").casefold() not in self.ignored:
                        if r["state"] == "CHANGES_REQUESTED": change_at = min(filter(None, [change_at, r.get("submittedAt")])) if change_at else r.get("submittedAt")
                        if r["state"] == "APPROVED" and r.get("submittedAt"): approvals.append(r["submittedAt"])
                if change_at:
                    totals["changes_requested_prs"] += 1
                    totals["approved_after_changes"] += int(any(a > change_at for a in approvals))

                for t in threads:
                    comments = self.thread_comments(t)
                    first_author = ((comments[0].get("author") or {}).get("login") if comments else None)
                    key = (first_author or "").casefold()
                    eligible = bool(first_author and key != self.username.casefold() and key not in self.ignored)
                    append_jsonl(self.files["review_threads"], {**common, "thread_id": t["id"], "path": t.get("path"), "line": t.get("line"), "start_line": t.get("startLine"), "diff_side": t.get("diffSide"), "is_resolved": t["isResolved"], "is_outdated": t["isOutdated"], "resolved_by_login": (t.get("resolvedBy") or {}).get("login"), "first_author_login": first_author, "eligible": eligible, "comment_count": len(comments)})
                    totals["threads"] += 1
                    totals["resolved_threads"] += int(t["isResolved"])
                    if eligible:
                        totals["eligible_threads"] += 1
                        totals["eligible_resolved"] += int(t["isResolved"])
                        reviewers[key] += 1
                    for pos, c in enumerate(comments, 1):
                        append_jsonl(self.files["review_comments"], {**common, "thread_id": t["id"], "comment_id": c["id"], "database_id": c.get("databaseId"), "position_in_thread": pos, "url": c["url"], "author_login": (c.get("author") or {}).get("login"), "body": c.get("body"), "state": c.get("state"), "reply_to_id": (c.get("replyTo") or {}).get("id"), "created_at": c["createdAt"], "updated_at": c["updatedAt"]})

                pr_agent = False
                for node in commits:
                    c = node["commit"]
                    author_login = ((c.get("author") or {}).get("user") or {}).get("login")
                    committer_login = ((c.get("committer") or {}).get("user") or {}).get("login")
                    identity = (author_login or committer_login or "").casefold()
                    is_agent = identity in self.agents
                    pr_agent |= is_agent
                    totals["commits"] += 1
                    totals["agent_commits"] += int(is_agent)
                    totals["unknown_commits"] += int(not identity)
                    if is_agent: agents[identity] += 1
                    append_jsonl(self.files["commits"], {**common, "oid": c["oid"], "url": c["url"], "headline": c["headline"], "message": c["message"], "authored_at": c["authoredDate"], "committed_at": c["committedDate"], "author_login": author_login, "author_name": (c.get("author") or {}).get("name"), "author_email": (c.get("author") or {}).get("email"), "committer_login": committer_login, "is_agent": is_agent, "agent_handle": identity if is_agent else None, "additions": c.get("additions"), "deletions": c.get("deletions"), "changed_files": c.get("changedFiles")})
                totals["prs_with_agent"] += int(pr_agent)
            except Exception as exc:
                append_jsonl(self.files["failures"], {"quarter": w.label, "repo": pr["repository"]["nameWithOwner"], "pr_number": pr["number"], "error": str(exc)})
                totals["failures"] += 1

        known = totals["commits"] - totals["unknown_commits"]
        human = known - totals["agent_commits"]
        return {
            "schema_version": 3, "generated_at": now().isoformat(), "user": self.username,
            "period": {"label": w.label, "start": str(w.start), "calendar_end": str(w.calendar_end), "effective_end": str(w.effective_end), "partial": w.effective_end < w.calendar_end},
            "files": {k: str(v.name) for k, v in self.files.items()},
            "raw_graphql_file": self.api.raw_path.name,
            "metrics": {
                "search_match_count": search_total, "prs": totals["prs"], "merged_prs": totals["merged_prs"], "merged_to_main": totals["merged_to_main"], "prs_with_jira_ids": totals["prs_with_jira"], "failures": totals["failures"],
                "review_threads": totals["threads"], "resolved_threads": totals["resolved_threads"], "resolution_rate_percentage": percentage(totals["resolved_threads"], totals["threads"]),
                "eligible_threads": totals["eligible_threads"], "eligible_resolved_threads": totals["eligible_resolved"], "eligible_resolution_rate_percentage": percentage(totals["eligible_resolved"], totals["eligible_threads"]),
                "changes_requested_prs": totals["changes_requested_prs"], "approved_after_changes_requested": totals["approved_after_changes"], "approval_after_changes_rate_percentage": percentage(totals["approved_after_changes"], totals["changes_requested_prs"]),
                "commits": totals["commits"], "human_commits": human, "agent_commits": totals["agent_commits"], "unknown_identity_commits": totals["unknown_commits"], "agent_percentage_of_known": percentage(totals["agent_commits"], known), "prs_with_agent_commits": totals["prs_with_agent"],
            },
            "reviewer_thread_distribution": [{"login": k, "threads": v, "percentage": percentage(v, sum(reviewers.values()))} for k, v in reviewers.most_common()],
            "agent_commit_breakdown": dict(agents),
            "tracked_reviewer": {"login": self.tracked, "threads": reviewers.get((self.tracked or "").casefold(), 0), "percentage": percentage(reviewers.get((self.tracked or "").casefold(), 0), sum(reviewers.values()))} if self.tracked else None,
        }


def args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build cached quarterly GitHub JSON/NDJSON review datasets")
    p.add_argument("--username", default=os.getenv("GITHUB_USER"))
    p.add_argument("--year", type=int, default=now().year)
    p.add_argument("--quarter", type=int, choices=(1, 2, 3, 4))
    p.add_argument("--overwrite", action="store_true")
    p.add_argument("--ignore-reviewer", action="append", default=[])
    p.add_argument("--track-reviewer")
    p.add_argument("--agent-handle", action="append")
    p.add_argument("--timeout", type=int, default=TIMEOUT)
    return p.parse_args()


def main() -> int:
    a, today = args(), now().date()
    if not a.username:
        print("error: set GITHUB_USER or pass --username", file=sys.stderr); return 2
    quarters = [a.quarter] if a.quarter else (list(range(1, current_quarter(today) + 1)) if a.year == today.year else [1, 2, 3, 4] if a.year < today.year else [])
    if not quarters:
        print("error: future years require an explicit completed quarter", file=sys.stderr); return 2
    root, user = Path(__file__).resolve().parent, safe(a.username)
    reports: list[dict[str, Any]] = []
    for q in quarters:
        summary = root / f"github_metrics_{user}_{a.year}Q{q}.json"
        if summary.exists() and not a.overwrite:
            print(f"Using cached quarter: {summary}", file=sys.stderr)
            reports.append(read_json(summary)); continue
        token = os.getenv("GITHUB_TOKEN")
        if not token:
            print("error: GITHUB_TOKEN required for uncached quarters", file=sys.stderr); return 2
        start, end = quarter_dates(a.year, q)
        effective = min(end, today)
        if start > effective:
            print(f"Skipping future quarter {a.year}Q{q}", file=sys.stderr); continue
        data_dir = root / f"github_metrics_{user}_{a.year}Q{q}_data"
        raw_file = root / f"github_metrics_{user}_{a.year}Q{q}_graphql.jsonl"
        if a.overwrite:
            paths_to_remove = [raw_file]
            if data_dir.exists():
                paths_to_remove.extend(data_dir.glob("*.jsonl"))
            for path in paths_to_remove:
                path.unlink(missing_ok=True)
        api = GraphQL(token, raw_file, a.timeout)
        report = Dataset(api, data_dir, a.username, normalize(a.ignore_reviewer), a.track_reviewer, normalize(a.agent_handle or AGENTS)).collect(Window(a.year, q, start, end, effective))
        write_json(summary, report); reports.append(report)
        print(f"Saved {summary}", file=sys.stderr)
    annual = {"schema_version": 3, "generated_at": now().isoformat(), "user": a.username, "year": a.year, "quarters": reports}
    annual_path = root / f"github_metrics_{user}_{a.year}_annual.json"
    write_json(annual_path, annual)
    print(json.dumps({"annual_file": str(annual_path), "quarters": [r["period"]["label"] for r in reports]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
