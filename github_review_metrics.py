#!/usr/bin/env python3
"""Quarterly GitHub review and commit metrics with local JSON caching.

Defaults:
- User: GITHUB_USER environment variable
- Year: current UTC year
- Scope: Q1 through the current quarter (or all four quarters for a past year)
- Cache/output: JSON files beside this script
- Existing quarterly JSON files are reused unless --overwrite is supplied

Authentication:
    export GITHUB_TOKEN=...
    export GITHUB_USER=octocat
    python github_review_metrics.py
"""

from __future__ import annotations

import argparse
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
PAGE_SIZE = 100
DEFAULT_TIMEOUT = 60
DEFAULT_AGENT_HANDLES = (
    "dependabot[bot]",
    "renovate[bot]",
    "github-actions[bot]",
    "copilot-swe-agent",
    "copilot-agent",
    "cursor-agent",
    "claude-code-bot",
    "coderabbitai[bot]",
)


def pct(numerator: int, denominator: int) -> Optional[float]:
    return round(numerator * 100.0 / denominator, 2) if denominator else None


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def current_quarter(today: Optional[date] = None) -> int:
    today = today or utc_now().date()
    return (today.month - 1) // 3 + 1


def quarter_bounds(year: int, quarter: int) -> tuple[date, date]:
    if quarter not in (1, 2, 3, 4):
        raise ValueError("quarter must be 1, 2, 3, or 4")
    start_month = 1 + (quarter - 1) * 3
    start = date(year, start_month, 1)
    if quarter == 4:
        end = date(year, 12, 31)
    else:
        end = date(year, start_month + 3, 1).fromordinal(
            date(year, start_month + 3, 1).toordinal() - 1
        )
    return start, end


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    if not cleaned:
        raise ValueError("username produces an empty file name")
    return cleaned


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")
    temporary.replace(path)


def normalize_handles(values: Iterable[str]) -> set[str]:
    return {value.strip().casefold() for value in values if value.strip()}


@dataclass(frozen=True)
class QuarterWindow:
    year: int
    quarter: int
    calendar_start: date
    calendar_end: date
    effective_end: date

    @property
    def label(self) -> str:
        return f"{self.year}Q{self.quarter}"

    @property
    def is_partial(self) -> bool:
        return self.effective_end < self.calendar_end


class GitHubGraphQLClient:
    def __init__(
        self,
        token: str,
        timeout: int = DEFAULT_TIMEOUT,
        max_retries: int = 4,
    ) -> None:
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "User-Agent": "quarterly-github-review-metrics/2.0",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )

    def execute(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self.session.post(
                    API_URL,
                    json={"query": query, "variables": variables},
                    timeout=self.timeout,
                )
                if response.status_code in (429, 502, 503, 504):
                    raise requests.HTTPError(
                        f"temporary HTTP {response.status_code}", response=response
                    )
                response.raise_for_status()
                payload = response.json()
                if payload.get("errors"):
                    raise RuntimeError(json.dumps(payload["errors"], ensure_ascii=False))
                data = payload.get("data")
                if not isinstance(data, dict):
                    raise RuntimeError("GitHub returned no GraphQL data")
                return data
            except (requests.RequestException, RuntimeError, ValueError) as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                time.sleep(min(2**attempt, 16))
        raise RuntimeError(f"GitHub API request failed: {last_error}") from last_error


class QuarterlyCollector:
    SEARCH_PRS = """
    query($query: String!, $cursor: String) {
      search(type: ISSUE, query: $query, first: 100, after: $cursor) {
        issueCount
        nodes {
          ... on PullRequest {
            id
            number
            url
            title
            createdAt
            merged
            mergedAt
            repository { nameWithOwner }
          }
        }
        pageInfo { hasNextPage endCursor }
      }
      rateLimit { cost remaining resetAt }
    }
    """

    THREADS = """
    query($id: ID!, $cursor: String) {
      node(id: $id) {
        ... on PullRequest {
          reviewThreads(first: 100, after: $cursor) {
            nodes {
              id
              isResolved
              isOutdated
              comments(first: 1) {
                nodes { author { login } createdAt }
              }
            }
            pageInfo { hasNextPage endCursor }
          }
        }
      }
    }
    """

    REVIEWS = """
    query($id: ID!, $cursor: String) {
      node(id: $id) {
        ... on PullRequest {
          reviews(first: 100, after: $cursor) {
            nodes { state submittedAt author { login } }
            pageInfo { hasNextPage endCursor }
          }
        }
      }
    }
    """

    COMMITS = """
    query($id: ID!, $cursor: String) {
      node(id: $id) {
        ... on PullRequest {
          commits(first: 100, after: $cursor) {
            nodes {
              commit {
                oid
                committedDate
                author { user { login } name email }
                committer { user { login } name email }
              }
            }
            pageInfo { hasNextPage endCursor }
          }
        }
      }
    }
    """

    def __init__(
        self,
        client: GitHubGraphQLClient,
        username: str,
        ignored_reviewers: set[str],
        tracked_reviewer: Optional[str],
        agent_handles: set[str],
        include_outdated_threads: bool,
    ) -> None:
        self.client = client
        self.username = username
        self.username_key = username.casefold()
        self.ignored_reviewers = ignored_reviewers
        self.tracked_reviewer = tracked_reviewer
        self.tracked_reviewer_key = tracked_reviewer.casefold() if tracked_reviewer else None
        self.agent_handles = agent_handles
        self.include_outdated_threads = include_outdated_threads

    def collect(self, window: QuarterWindow) -> dict[str, Any]:
        prs, search_total = self._find_prs(window)
        totals: Counter[str] = Counter()
        reviewer_threads: Counter[str] = Counter()
        ignored_threads: Counter[str] = Counter()
        agent_commits: Counter[str] = Counter()
        failures: list[dict[str, str]] = []

        totals["prs_opened"] = len(prs)
        totals["prs_merged"] = sum(1 for pr in prs if pr["merged"])

        for index, pr in enumerate(prs, start=1):
            label = f'{pr["repository"]["nameWithOwner"]}#{pr["number"]}'
            print(f"[{window.label} {index}/{len(prs)}] {label}", file=sys.stderr)
            try:
                threads = self._all_connection(pr["id"], self.THREADS, "reviewThreads")
                reviews = self._all_connection(pr["id"], self.REVIEWS, "reviews")
                commits = self._all_connection(pr["id"], self.COMMITS, "commits")
                self._process_threads(threads, totals, reviewer_threads, ignored_threads)
                self._process_reviews(reviews, totals)
                self._process_commits(commits, totals, agent_commits)
                if any(self._commit_login(node) in self.agent_handles for node in commits):
                    totals["prs_with_agent_commits"] += 1
            except Exception as exc:  # continue so one inaccessible PR does not discard the quarter
                failures.append({"pull_request": label, "error": str(exc)})

        eligible_comments = totals["eligible_review_threads"]
        tracked_count = (
            reviewer_threads.get(self.tracked_reviewer_key, 0)
            if self.tracked_reviewer_key
            else 0
        )
        approval_denominator = totals["prs_with_changes_requested"]
        known_commits = totals["human_commits"] + totals["agent_commits"]

        return {
            "schema_version": 2,
            "generated_at": utc_now().isoformat(),
            "user": self.username,
            "period": {
                "year": window.year,
                "quarter": window.quarter,
                "label": window.label,
                "calendar_start": window.calendar_start.isoformat(),
                "calendar_end": window.calendar_end.isoformat(),
                "effective_end": window.effective_end.isoformat(),
                "partial_quarter": window.is_partial,
            },
            "configuration": {
                "ignored_reviewers": sorted(self.ignored_reviewers),
                "tracked_reviewer": self.tracked_reviewer,
                "agent_handles": sorted(self.agent_handles),
                "include_outdated_threads": self.include_outdated_threads,
                "thread_attribution": "author of the first comment in each review thread",
            },
            "pull_requests": {
                "opened": totals["prs_opened"],
                "merged": totals["prs_merged"],
                "merge_rate_percentage": pct(totals["prs_merged"], totals["prs_opened"]),
                "search_match_count": search_total,
                "processed": totals["prs_opened"] - len(failures),
                "failed": len(failures),
            },
            "review_threads": {
                "all": totals["all_review_threads"],
                "all_resolved": totals["all_resolved_threads"],
                "all_resolution_rate_percentage": pct(
                    totals["all_resolved_threads"], totals["all_review_threads"]
                ),
                "eligible": eligible_comments,
                "eligible_resolved": totals["eligible_resolved_threads"],
                "eligible_resolution_rate_percentage": pct(
                    totals["eligible_resolved_threads"], eligible_comments
                ),
                "ignored": totals["ignored_review_threads"],
                "unknown_author": totals["unknown_author_threads"],
                "outdated_excluded": totals["outdated_threads_excluded"],
                "by_reviewer": self._distribution(reviewer_threads),
                "ignored_by_reviewer": dict(sorted(ignored_threads.items())),
                "tracked_reviewer": (
                    {
                        "login": self.tracked_reviewer,
                        "threads": tracked_count,
                        "share_percentage": pct(tracked_count, eligible_comments),
                    }
                    if self.tracked_reviewer
                    else None
                ),
            },
            "review_outcomes": {
                "prs_with_changes_requested": approval_denominator,
                "prs_approved_after_changes_requested": totals[
                    "prs_approved_after_changes_requested"
                ],
                "approval_after_changes_rate_percentage": pct(
                    totals["prs_approved_after_changes_requested"], approval_denominator
                ),
            },
            "commits": {
                "total": totals["total_commits"],
                "known_identity": known_commits,
                "unknown_identity": totals["unknown_commits"],
                "human": totals["human_commits"],
                "agent": totals["agent_commits"],
                "human_percentage_of_known": pct(totals["human_commits"], known_commits),
                "agent_percentage_of_known": pct(totals["agent_commits"], known_commits),
                "agent_percentage_of_total": pct(
                    totals["agent_commits"], totals["total_commits"]
                ),
                "agent_breakdown": dict(sorted(agent_commits.items())),
                "prs_with_agent_commits": totals["prs_with_agent_commits"],
                "agent_assisted_pr_rate_percentage": pct(
                    totals["prs_with_agent_commits"], totals["prs_opened"]
                ),
            },
            "failures": failures,
            "limitations": [
                "A resolved thread is attributed to the author of its first comment.",
                "Agent detection is handle-based and cannot identify AI work committed under a human account.",
                "The GitHub GraphQL search connection exposes at most 1,000 results per query.",
            ],
        }

    def _find_prs(self, window: QuarterWindow) -> tuple[list[dict[str, Any]], int]:
        search = (
            f"author:{self.username} is:pr "
            f"created:{window.calendar_start.isoformat()}..{window.effective_end.isoformat()} "
            "sort:created-asc"
        )
        cursor: Optional[str] = None
        nodes: list[dict[str, Any]] = []
        total = 0
        while True:
            data = self.client.execute(self.SEARCH_PRS, {"query": search, "cursor": cursor})
            connection = data["search"]
            total = connection["issueCount"]
            nodes.extend(node for node in connection["nodes"] if node)
            page = connection["pageInfo"]
            if not page["hasNextPage"]:
                break
            cursor = page["endCursor"]
        if total > 1000:
            raise RuntimeError(
                f"Quarter {window.label} matched {total} PRs; GitHub search exposes only 1,000. "
                "Split the period or add repository/org filters."
            )
        return nodes, total

    def _all_connection(self, pr_id: str, query: str, connection_name: str) -> list[dict[str, Any]]:
        cursor: Optional[str] = None
        nodes: list[dict[str, Any]] = []
        while True:
            data = self.client.execute(query, {"id": pr_id, "cursor": cursor})
            pr = data.get("node")
            if not pr:
                raise RuntimeError("Pull request is unavailable")
            connection = pr[connection_name]
            nodes.extend(node for node in connection["nodes"] if node)
            page = connection["pageInfo"]
            if not page["hasNextPage"]:
                return nodes
            cursor = page["endCursor"]

    def _process_threads(
        self,
        threads: list[dict[str, Any]],
        totals: Counter[str],
        reviewer_threads: Counter[str],
        ignored_threads: Counter[str],
    ) -> None:
        for thread in threads:
            if thread["isOutdated"] and not self.include_outdated_threads:
                totals["outdated_threads_excluded"] += 1
                continue
            totals["all_review_threads"] += 1
            if thread["isResolved"]:
                totals["all_resolved_threads"] += 1
            comments = thread["comments"]["nodes"]
            author = comments[0].get("author") if comments else None
            login = author.get("login") if author else None
            if not login:
                totals["unknown_author_threads"] += 1
                continue
            key = login.casefold()
            if key == self.username_key:
                continue
            if key in self.ignored_reviewers:
                totals["ignored_review_threads"] += 1
                ignored_threads[key] += 1
                continue
            totals["eligible_review_threads"] += 1
            reviewer_threads[key] += 1
            if thread["isResolved"]:
                totals["eligible_resolved_threads"] += 1

    def _process_reviews(self, reviews: list[dict[str, Any]], totals: Counter[str]) -> None:
        ordered = sorted(
            (review for review in reviews if review.get("submittedAt")),
            key=lambda review: review["submittedAt"],
        )
        change_index: Optional[int] = None
        approval_after = False
        for index, review in enumerate(ordered):
            author = review.get("author") or {}
            login = (author.get("login") or "").casefold()
            if login in self.ignored_reviewers:
                continue
            if review["state"] == "CHANGES_REQUESTED" and change_index is None:
                change_index = index
            elif review["state"] == "APPROVED" and change_index is not None and index > change_index:
                approval_after = True
        if change_index is not None:
            totals["prs_with_changes_requested"] += 1
            if approval_after:
                totals["prs_approved_after_changes_requested"] += 1

    @staticmethod
    def _commit_login(node: dict[str, Any]) -> Optional[str]:
        commit = node.get("commit") or {}
        author = commit.get("author") or {}
        committer = commit.get("committer") or {}
        user = author.get("user") or committer.get("user") or {}
        login = user.get("login")
        return login.casefold() if login else None

    def _process_commits(
        self,
        commits: list[dict[str, Any]],
        totals: Counter[str],
        agent_commits: Counter[str],
    ) -> None:
        for node in commits:
            totals["total_commits"] += 1
            login = self._commit_login(node)
            if not login:
                totals["unknown_commits"] += 1
            elif login in self.agent_handles:
                totals["agent_commits"] += 1
                agent_commits[login] += 1
            else:
                totals["human_commits"] += 1

    @staticmethod
    def _distribution(counts: Counter[str]) -> list[dict[str, Any]]:
        total = sum(counts.values())
        return [
            {
                "login": login,
                "threads": count,
                "share_percentage": pct(count, total),
            }
            for login, count in counts.most_common()
        ]


def aggregate_annual(
    username: str, year: int, quarter_reports: list[dict[str, Any]]
) -> dict[str, Any]:
    sums: Counter[str] = Counter()
    reviewer_counts: Counter[str] = Counter()
    agent_counts: Counter[str] = Counter()

    for report in quarter_reports:
        prs = report["pull_requests"]
        threads = report["review_threads"]
        outcomes = report["review_outcomes"]
        commits = report["commits"]
        mapping = {
            "prs_opened": prs["opened"],
            "prs_merged": prs["merged"],
            "threads_all": threads["all"],
            "threads_all_resolved": threads["all_resolved"],
            "threads_eligible": threads["eligible"],
            "threads_eligible_resolved": threads["eligible_resolved"],
            "prs_changes_requested": outcomes["prs_with_changes_requested"],
            "prs_approved_after_changes": outcomes["prs_approved_after_changes_requested"],
            "commits_total": commits["total"],
            "commits_known": commits["known_identity"],
            "commits_unknown": commits["unknown_identity"],
            "commits_human": commits["human"],
            "commits_agent": commits["agent"],
            "prs_agent": commits["prs_with_agent_commits"],
        }
        sums.update(mapping)
        for item in threads["by_reviewer"]:
            reviewer_counts[item["login"]] += item["threads"]
        agent_counts.update(commits["agent_breakdown"])

    return {
        "schema_version": 2,
        "generated_at": utc_now().isoformat(),
        "user": username,
        "year": year,
        "quarters_included": [report["period"]["label"] for report in quarter_reports],
        "quarterly_reports": quarter_reports,
        "annual_summary": {
            "prs_opened": sums["prs_opened"],
            "prs_merged": sums["prs_merged"],
            "merge_rate_percentage": pct(sums["prs_merged"], sums["prs_opened"]),
            "review_threads_all": sums["threads_all"],
            "review_threads_all_resolved": sums["threads_all_resolved"],
            "all_resolution_rate_percentage": pct(
                sums["threads_all_resolved"], sums["threads_all"]
            ),
            "review_threads_eligible": sums["threads_eligible"],
            "review_threads_eligible_resolved": sums["threads_eligible_resolved"],
            "eligible_resolution_rate_percentage": pct(
                sums["threads_eligible_resolved"], sums["threads_eligible"]
            ),
            "prs_with_changes_requested": sums["prs_changes_requested"],
            "prs_approved_after_changes_requested": sums["prs_approved_after_changes"],
            "approval_after_changes_rate_percentage": pct(
                sums["prs_approved_after_changes"], sums["prs_changes_requested"]
            ),
            "commits_total": sums["commits_total"],
            "commits_human": sums["commits_human"],
            "commits_agent": sums["commits_agent"],
            "commits_unknown_identity": sums["commits_unknown"],
            "human_commit_percentage_of_known": pct(
                sums["commits_human"], sums["commits_known"]
            ),
            "agent_commit_percentage_of_known": pct(
                sums["commits_agent"], sums["commits_known"]
            ),
            "agent_commit_percentage_of_total": pct(
                sums["commits_agent"], sums["commits_total"]
            ),
            "prs_with_agent_commits": sums["prs_agent"],
            "agent_assisted_pr_rate_percentage": pct(
                sums["prs_agent"], sums["prs_opened"]
            ),
            "review_threads_by_reviewer": QuarterlyCollector._distribution(reviewer_counts),
            "agent_commit_breakdown": dict(sorted(agent_counts.items())),
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate cached quarterly and annual GitHub contribution metrics."
    )
    parser.add_argument(
        "--username",
        default=os.getenv("GITHUB_USER"),
        help="GitHub login; defaults to GITHUB_USER.",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=utc_now().year,
        help="Review year; defaults to the current UTC year.",
    )
    parser.add_argument(
        "--quarter",
        type=int,
        choices=(1, 2, 3, 4),
        help="Generate only this quarter. By default generates Q1 through the current quarter.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Ignore cached quarterly JSON and query GitHub again.",
    )
    parser.add_argument(
        "--ignore-reviewer",
        action="append",
        default=[],
        help="Reviewer login to exclude; repeat for multiple users.",
    )
    parser.add_argument(
        "--track-reviewer",
        default=None,
        help="Reviewer login whose eligible thread share should be reported.",
    )
    parser.add_argument(
        "--agent-handle",
        action="append",
        default=None,
        help="Agent/bot login; repeat to replace the built-in defaults.",
    )
    parser.add_argument(
        "--include-outdated-threads",
        action="store_true",
        help="Include outdated review threads in resolution metrics.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"HTTP timeout in seconds (default: {DEFAULT_TIMEOUT}).",
    )
    return parser.parse_args()


def requested_quarters(year: int, selected: Optional[int], today: date) -> list[int]:
    if selected:
        return [selected]
    if year < today.year:
        return [1, 2, 3, 4]
    if year == today.year:
        return list(range(1, current_quarter(today) + 1))
    raise ValueError("A future year requires an explicit --quarter and is not a review period yet")


def main() -> int:
    args = parse_args()
    if not args.username:
        print("error: set GITHUB_USER or pass --username", file=sys.stderr)
        return 2
    if args.timeout <= 0:
        print("error: --timeout must be positive", file=sys.stderr)
        return 2

    today = utc_now().date()
    try:
        quarters = requested_quarters(args.year, args.quarter, today)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    script_dir = Path(__file__).resolve().parent
    user_file = safe_name(args.username)
    ignored = normalize_handles(args.ignore_reviewer)
    agents = normalize_handles(args.agent_handle or DEFAULT_AGENT_HANDLES)
    reports: list[dict[str, Any]] = []
    client: Optional[GitHubGraphQLClient] = None
    collector: Optional[QuarterlyCollector] = None

    for quarter in quarters:
        cache_path = script_dir / f"github_metrics_{user_file}_{args.year}Q{quarter}.json"
        if cache_path.exists() and not args.overwrite:
            try:
                report = load_json(cache_path)
                if report.get("user", "").casefold() != args.username.casefold():
                    raise ValueError("cached username does not match")
                print(f"Using cached report: {cache_path}", file=sys.stderr)
                reports.append(report)
                continue
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                print(f"Ignoring invalid cache {cache_path}: {exc}", file=sys.stderr)

        if client is None:
            token = os.getenv("GITHUB_TOKEN")
            if not token:
                print(
                    "error: GITHUB_TOKEN is required because at least one quarter is not cached",
                    file=sys.stderr,
                )
                return 2
            client = GitHubGraphQLClient(token=token, timeout=args.timeout)
            collector = QuarterlyCollector(
                client=client,
                username=args.username,
                ignored_reviewers=ignored,
                tracked_reviewer=args.track_reviewer,
                agent_handles=agents,
                include_outdated_threads=args.include_outdated_threads,
            )

        start, calendar_end = quarter_bounds(args.year, quarter)
        effective_end = min(calendar_end, today)
        if start > effective_end:
            print(f"Skipping future quarter {args.year}Q{quarter}", file=sys.stderr)
            continue
        window = QuarterWindow(args.year, quarter, start, calendar_end, effective_end)
        assert collector is not None
        report = collector.collect(window)
        atomic_write_json(cache_path, report)
        print(f"Saved: {cache_path}", file=sys.stderr)
        reports.append(report)

    if not reports:
        print("error: no quarter reports were generated", file=sys.stderr)
        return 1

    annual = aggregate_annual(args.username, args.year, reports)
    annual_path = script_dir / f"github_metrics_{user_file}_{args.year}_annual.json"
    atomic_write_json(annual_path, annual)
    print(f"Saved annual review: {annual_path}", file=sys.stderr)
    print(json.dumps({
        "user": args.username,
        "year": args.year,
        "quarters": annual["quarters_included"],
        "annual_file": str(annual_path),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
