#!/usr/bin/env python3

import os
import requests
import sys
from collections import defaultdict

GITHUB_API = "https://api.github.com/graphql"

TOKEN = os.getenv("GITHUB_TOKEN")

if not TOKEN:
    print("Missing GITHUB_TOKEN")
    sys.exit(1)

HEADERS = {
    "Authorization": f"Bearer {TOKEN}"
}


def graphql(query, variables=None):
    response = requests.post(
        GITHUB_API,
        json={
            "query": query,
            "variables": variables or {}
        },
        headers=HEADERS,
        timeout=60
    )

    response.raise_for_status()

    payload = response.json()

    if "errors" in payload:
        raise RuntimeError(payload["errors"])

    return payload["data"]


def get_authored_prs(username, limit=100):
    query = """
    query($login:String!, $count:Int!) {
      user(login:$login) {
        pullRequests(
          first:$count,
          orderBy:{field:CREATED_AT,direction:DESC}
        ) {
          nodes {
            number
            repository {
              name
              owner {
                login
              }
            }
            merged
          }
        }
      }
    }
    """

    data = graphql(query, {
        "login": username,
        "count": limit
    })

    return data["user"]["pullRequests"]["nodes"]


def get_pr_review_data(owner, repo, number):
    query = """
    query($owner:String!, $repo:String!, $number:Int!) {
      repository(owner:$owner, name:$repo) {
        pullRequest(number:$number) {

          reviewThreads(first:100) {
            nodes {
              isResolved
            }
          }

          reviews(first:100) {
            nodes {
              state
            }
          }
        }
      }
    }
    """

    return graphql(query, {
        "owner": owner,
        "repo": repo,
        "number": number
    })


def analyze_user(username):

    prs = get_authored_prs(username)

    metrics = defaultdict(int)

    metrics["prs_opened"] = len(prs)

    for pr in prs:

        owner = pr["repository"]["owner"]["login"]
        repo = pr["repository"]["name"]
        number = pr["number"]

        if pr["merged"]:
            metrics["prs_merged"] += 1

        try:
            data = get_pr_review_data(
                owner,
                repo,
                number
            )

            pr_data = data["repository"]["pullRequest"]

            threads = pr_data["reviewThreads"]["nodes"]

            for thread in threads:
                metrics["threads_total"] += 1

                if thread["isResolved"]:
                    metrics["threads_resolved"] += 1

            reviews = pr_data["reviews"]["nodes"]

            had_changes_requested = False
            had_approval = False

            for review in reviews:

                state = review["state"]

                if state == "CHANGES_REQUESTED":
                    had_changes_requested = True
                    metrics["changes_requested"] += 1

                if state == "APPROVED":
                    had_approval = True

            if had_changes_requested and had_approval:
                metrics["changes_resolved"] += 1

        except Exception as e:
            print(
                f"Skipping {owner}/{repo}#{number}: {e}",
                file=sys.stderr
            )

    results = {
        "user": username,
        "prs_opened": metrics["prs_opened"],
        "prs_merged": metrics["prs_merged"],
        "merge_rate": round(
            metrics["prs_merged"] /
            max(metrics["prs_opened"], 1) * 100,
            2
        ),
        "review_threads_total":
            metrics["threads_total"],
        "review_threads_resolved":
            metrics["threads_resolved"],
        "resolution_rate": round(
            metrics["threads_resolved"] /
            max(metrics["threads_total"], 1) * 100,
            2
        ),
        "changes_requested":
            metrics["changes_requested"],
        "changes_resolved":
            metrics["changes_resolved"],
        "approval_after_changes_rate": round(
            metrics["changes_resolved"] /
            max(metrics["changes_requested"], 1) * 100,
            2
        )
    }

    return results


if __name__ == "__main__":

    if len(sys.argv) != 2:
        print(
            "Usage: python github_review_metrics.py USERNAME"
        )
        sys.exit(1)

    import json

    print(
        json.dumps(
            analyze_user(sys.argv[1]),
            indent=2
        )
    )
