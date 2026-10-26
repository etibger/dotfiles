#!/usr/bin/env python3
"""Copy issues and comments from this repository's GitHub mirror to Gitea."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Any


GH_REPO = "etibger/agentic_tools"
GITEA_OWNER = "tibger01"
GITEA_REPO = "agentic_tools"
GITEA_API = "http://192.168.10.150:3005/api/v1"
PAGE_SIZE = 50
MARKER_RE = re.compile(
    r"(?:\n\n)?---\nSource: GitHub issue #(?P<number>\d+) \u2014 "
    r"(?P<url>https://github\.com/etibger/agentic_tools/issues/\d+)\n"
    r"<!-- github-issue-sync:v1 number=(?P=number) url=(?P=url) "
    r"digest=(?P<digest>[0-9a-f]{64}) -->$"
)
SOURCE_LINE_RE = re.compile(
    r"(?m)^Source: GitHub issue #(?P<number>\d+) \u2014 "
    r"https://github\.com/etibger/agentic_tools/issues/(?P=number)$"
)
COMMENT_MARKER_RE = re.compile(
    r"(?:\n\n)?<!-- github-comment-sync:v1 issue=(?P<issue>\d+) "
    r"comment=(?P<comment>\d+) digest=(?P<digest>[0-9a-f]{64}) -->$"
)


class SyncError(Exception):
    pass


def gh_json_lines(endpoint: str) -> list[dict[str, Any]]:
    """Read every page through the user's authenticated gh CLI session."""
    try:
        result = subprocess.run(
            ["gh", "api", "--paginate", "--jq", ".[]", endpoint],
            check=True,
            capture_output=True,
            text=True,
            env={key: value for key, value in os.environ.items() if key != "GITEA_TOKEN"},
        )
    except FileNotFoundError as exc:
        raise SyncError("gh was not found; install and authenticate GitHub CLI first") from exc
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or "GitHub API request failed"
        raise SyncError(f"gh api failed for {endpoint}: {detail}") from exc
    decoder = json.JSONDecoder()
    rows: list[dict[str, Any]] = []
    offset = 0
    try:
        while offset < len(result.stdout):
            while offset < len(result.stdout) and result.stdout[offset].isspace():
                offset += 1
            if offset == len(result.stdout):
                break
            value, offset = decoder.raw_decode(result.stdout, offset)
            rows.append(value)
    except json.JSONDecodeError as exc:
        raise SyncError(f"gh returned invalid JSON for {endpoint}") from exc
    return rows


class Gitea:
    def __init__(self, token: str):
        self.token = token

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        url = GITEA_API + path
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/json",
        }
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                raw = response.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8", errors="replace")
            except Exception:
                detail = ""
            detail = detail.replace(self.token, "[redacted]")
            raise SyncError(
                f"Gitea {method} {path} returned HTTP {exc.code}"
                + (f": {detail[:500]}" if detail else "")
            ) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise SyncError(f"Gitea {method} {path} failed: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise SyncError(f"Gitea returned invalid JSON for {method} {path}") from exc

    def pages(self, path: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        page = 1
        while True:
            separator = "&" if "?" in path else "?"
            result = self.request(
                "GET", f"{path}{separator}limit={PAGE_SIZE}&page={page}"
            )
            if not isinstance(result, list):
                raise SyncError(f"Unexpected paginated response from {path}")
            rows.extend(result)
            if len(result) < PAGE_SIZE:
                return rows
            page += 1


def source_issues() -> list[dict[str, Any]]:
    issues = gh_json_lines(
        f"repos/{GH_REPO}/issues?state=all&per_page=100&sort=created&direction=asc"
    )
    return [issue for issue in issues if "pull_request" not in issue]


def source_comments(number: int) -> list[dict[str, Any]]:
    comments = gh_json_lines(
        f"repos/{GH_REPO}/issues/{number}/comments?per_page=100"
    )
    return sorted(comments, key=lambda c: (c.get("created_at", ""), c.get("id", 0)))


def progress(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def parse_issue_mapping(body: str) -> tuple[int, str, str, str] | None:
    match = MARKER_RE.search(body or "")
    if not match:
        return None
    return (
        int(match.group("number")),
        match.group("url"),
        match.group("digest"),
        (body or "")[: match.start()],
    )


def normalized_state(issue: dict[str, Any]) -> str:
    state = str(issue.get("state", "")).lower()
    if state in ("closed", "open"):
        return state
    return "closed" if issue.get("closed") else "open"


def label_names(labels: list[dict[str, Any]]) -> list[str]:
    return sorted({str(label.get("name", "")) for label in labels if label.get("name")})


def fingerprint(title: str, body: str, state: str, labels: list[str]) -> str:
    value = {
        "title": title,
        "body": body,
        "state": state,
        "labels": sorted(labels, key=str.casefold),
    }
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def rendered_body(issue: dict[str, Any], labels: list[str]) -> str:
    body = issue.get("body") or ""
    number = int(issue["number"])
    url = str(issue["html_url"])
    digest = fingerprint(str(issue.get("title") or ""), body, normalized_state(issue), labels)
    footer = (
        f"---\nSource: GitHub issue #{number} \u2014 {url}\n"
        f"<!-- github-issue-sync:v1 number={number} url={url} digest={digest} -->"
    )
    return body + ("\n\n" if body else "") + footer


def matching_labels(
    issue: dict[str, Any], target_labels: list[dict[str, Any]]
) -> tuple[list[int], list[str], list[str]]:
    target_by_name = {str(label.get("name", "")).casefold(): label for label in target_labels}
    ids: list[int] = []
    names: list[str] = []
    missing: list[str] = []
    for label in issue.get("labels", []):
        name = str(label.get("name", ""))
        target = target_by_name.get(name.casefold())
        if target is None:
            if name:
                missing.append(name)
            continue
        ids.append(int(target["id"]))
        names.append(str(target["name"]))
    return ids, sorted(set(names), key=str.casefold), sorted(set(missing), key=str.casefold)


def missing_label_specs(
    issues: list[dict[str, Any]], target_labels: list[dict[str, Any]]
) -> dict[str, dict[str, str]]:
    existing_names = {str(label.get("name", "")).casefold() for label in target_labels}
    missing: dict[str, dict[str, str]] = {}
    for issue in issues:
        for label in issue.get("labels", []):
            name = str(label.get("name", ""))
            key = name.casefold()
            if name and key not in existing_names and key not in missing:
                color = str(label.get("color", "bfdadc")).lstrip("#") or "bfdadc"
                missing[key] = {
                    "name": name,
                    "color": f"#{color}",
                    "description": str(label.get("description") or ""),
                }
    return missing


def mapped_target_issues(gitea: Gitea) -> dict[int, dict[str, Any]]:
    rows = gitea.pages(f"/repos/{GITEA_OWNER}/{GITEA_REPO}/issues?state=all")
    mapping: dict[int, dict[str, Any]] = {}
    for row in rows:
        if row.get("pull_request"):
            continue
        parsed = parse_issue_mapping(str(row.get("body") or ""))
        if not parsed:
            source_line = SOURCE_LINE_RE.search(str(row.get("body") or ""))
            if not source_line:
                continue
            # The visible mapping survived but its sync marker was edited or removed.
            # Keep it mapped and protected rather than creating a duplicate.
            number = int(source_line.group("number"))
            digest = None
            base_body = str(row.get("body") or "")
        else:
            number, url, digest, base_body = parsed
            if url != f"https://github.com/{GH_REPO}/issues/{number}":
                continue
        if number in mapping:
            raise SyncError(f"Multiple Gitea issues map to GitHub issue #{number}; resolve the duplicate manually")
        row["_sync_digest"] = digest
        row["_sync_base_body"] = base_body
        mapping[number] = row
    return mapping


def target_comments(gitea: Gitea, index: int) -> dict[tuple[int, int], dict[str, Any]]:
    comments = gitea.pages(
        f"/repos/{GITEA_OWNER}/{GITEA_REPO}/issues/{index}/comments"
    )
    found: dict[tuple[int, int], dict[str, Any]] = {}
    for comment in comments:
        body = str(comment.get("body") or "")
        match = COMMENT_MARKER_RE.search(body)
        if match:
            key = (int(match.group("issue")), int(match.group("comment")))
            if key in found:
                raise SyncError(f"Multiple Gitea comments map to GitHub comment #{key[1]}; resolve the duplicate manually")
            found[key] = {
                "id": int(comment["id"]),
                "digest": match.group("digest"),
                "content": body[: match.start()],
            }
    return found


def comment_content(comment: dict[str, Any]) -> str:
    user = comment.get("user") or {}
    login = str(user.get("login") or "unknown")
    timestamp = str(comment.get("created_at") or "unknown time")
    body = str(comment.get("body") or "")
    return f"GitHub comment by @{login} ({timestamp}):\n\n{body}"


def comment_body(issue_number: int, comment: dict[str, Any]) -> str:
    comment_id = int(comment["id"])
    content = comment_content(comment)
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return (
        f"{content}\n\n"
        f"<!-- github-comment-sync:v1 issue={issue_number} comment={comment_id} digest={digest} -->"
    )


def ensure_api_access(gitea: Gitea) -> None:
    # Read checks verify the same authenticated principal and repo before any write.
    user = gitea.request("GET", "/user")
    repo = gitea.request("GET", f"/repos/{GITEA_OWNER}/{GITEA_REPO}")
    issues = gitea.request(
        "GET", f"/repos/{GITEA_OWNER}/{GITEA_REPO}/issues?state=all&limit=1&page=1"
    )
    permissions = repo.get("permissions") or {}
    if not isinstance(issues, list):
        raise SyncError("Gitea issue list endpoint returned an unexpected response")
    if not permissions.get("push") and not permissions.get("admin"):
        raise SyncError(
            "Gitea token can list issues but lacks repository write permission; "
            "grant push/write access to create issues and comments"
        )
    print(f"Gitea access: authenticated as {user.get('login', 'unknown')}; issue list and write permission confirmed.")


def plan_issue(
    source: dict[str, Any],
    target: dict[str, Any] | None,
    target_label_names: list[str],
) -> str:
    if target is None:
        return "create"
    current_labels = label_names(target.get("labels") or [])
    current_body = str(target.get("_sync_base_body", ""))
    current_digest = fingerprint(
        str(target.get("title") or ""),
        current_body,
        normalized_state(target),
        current_labels,
    )
    if current_digest != target.get("_sync_digest"):
        return "manual-edit; issue fields left unchanged"

    desired_body = str(source.get("body") or "")
    desired_title = str(source.get("title") or "")
    desired_state = normalized_state(source)
    issue_changed = (
        str(target.get("title") or "") != desired_title
        or current_body != desired_body
        or normalized_state(target) != desired_state
        or sorted(current_labels, key=str.casefold)
        != sorted(target_label_names, key=str.casefold)
    )
    return "update" if issue_changed else "up to date"


def run(apply: bool) -> int:
    token = os.environ.get("GITEA_TOKEN", "")
    if not token:
        raise SyncError("GITEA_TOKEN is missing; retrieve it from the macOS Keychain via the zsh function")
    gitea = Gitea(token)
    progress("Checking Gitea access...")
    ensure_api_access(gitea)

    progress("Fetching GitHub issues and Gitea issue mappings...")
    source = source_issues()
    existing = mapped_target_issues(gitea)
    target_labels = gitea.pages(f"/repos/{GITEA_OWNER}/{GITEA_REPO}/labels")
    new_label_specs = missing_label_specs(source, target_labels)
    progress(f"Planning {len(source)} issues and checking comments (0/{len(source)})...")
    plans: list[dict[str, Any]] = []

    for issue_index, issue in enumerate(source, start=1):
        number = int(issue["number"])
        label_ids, target_names, missing_labels = matching_labels(issue, target_labels)
        target = existing.get(number)
        action = plan_issue(issue, target, target_names)
        source_issue_comments = source_comments(number)
        target_comment_map = target_comments(gitea, int(target["number"])) if target else {}
        comment_additions: list[dict[str, Any]] = []
        comment_updates: list[dict[str, Any]] = []
        protected_comments = 0
        for comment in source_issue_comments:
            key = (number, int(comment["id"]))
            copied = target_comment_map.get(key)
            if copied is None:
                comment_additions.append(comment)
                continue
            current_hash = hashlib.sha256(copied["content"].encode("utf-8")).hexdigest()
            if current_hash != copied["digest"]:
                protected_comments += 1
            elif copied["content"] != comment_content(comment):
                comment_updates.append({"source": comment, "target": copied})
        plans.append(
            {
                "source": issue,
                "target": target,
                "labels": label_ids,
                "label_names": target_names,
                "missing_labels": missing_labels,
                "action": action,
                "comment_additions": comment_additions,
                "comment_updates": comment_updates,
                "protected_comments": protected_comments,
            }
        )
        if issue_index == len(source) or issue_index % 5 == 0:
            progress(f"Planning issues and comments ({issue_index}/{len(source)})...")

    creates = sum(p["action"] == "create" for p in plans)
    updates = sum(p["action"] == "update" for p in plans)
    manual = sum(p["action"].startswith("manual-edit") for p in plans)
    comments = sum(len(p["comment_additions"]) for p in plans)
    comment_updates = sum(len(p["comment_updates"]) for p in plans)
    protected_comments = sum(p["protected_comments"] for p in plans)
    print(
        f"{'Apply' if apply else 'Dry run'}: {len(source)} GitHub issues; "
        f"{creates} to create, {updates} safe updates, {manual} protected from edits, "
        f"{comments} comments to add, {comment_updates} safe comment updates, "
        f"{protected_comments} manually edited comments protected, "
        f"{len(new_label_specs)} labels to create."
    )
    for plan in plans:
        issue = plan["source"]
        number = int(issue["number"])
        extra = []
        if plan["comment_additions"]:
            extra.append(f"{len(plan['comment_additions'])} comments to add")
        if plan["comment_updates"]:
            extra.append(f"{len(plan['comment_updates'])} comment updates")
        if plan["protected_comments"]:
            extra.append(f"{plan['protected_comments']} edited comments protected")
        if plan["missing_labels"]:
            extra.append(f"labels to create: {', '.join(plan['missing_labels'])}")
        suffix = f" ({'; '.join(extra)})" if extra else ""
        print(f"  #{number}: {plan['action']}{suffix}")

    if not apply:
        print("No Gitea changes made. Run harmonize-github-issues --apply to apply this sync.")
        return 0

    progress("Applying missing Gitea labels...")
    for spec in new_label_specs.values():
        gitea.request(
            "POST",
            f"/repos/{GITEA_OWNER}/{GITEA_REPO}/labels",
            spec,
        )
    if new_label_specs:
        target_labels = gitea.pages(f"/repos/{GITEA_OWNER}/{GITEA_REPO}/labels")
        for plan in plans:
            label_ids, label_names_for_target, missing = matching_labels(
                plan["source"], target_labels
            )
            plan["labels"] = label_ids
            plan["label_names"] = label_names_for_target
            plan["missing_labels"] = missing

    progress(f"Applying issue and comment changes (0/{len(plans)} issues)...")
    for plan_index, plan in enumerate(plans, start=1):
        source_issue = plan["source"]
        number = int(source_issue["number"])
        target = plan["target"]
        action = plan["action"]
        if target is None:
            payload = {
                "title": str(source_issue.get("title") or ""),
                "body": rendered_body(source_issue, plan["label_names"]),
                "closed": normalized_state(source_issue) == "closed",
                "labels": plan["labels"],
            }
            target = gitea.request(
                "POST", f"/repos/{GITEA_OWNER}/{GITEA_REPO}/issues", payload
            )
            plan["target"] = target
            print(f"Created Gitea issue #{target['number']} for GitHub #{number}.")
        elif action == "update":
            target_index = int(target["number"])
            # Replace labels first; the body marker is updated last as the sync checkpoint.
            gitea.request(
                "PUT",
                f"/repos/{GITEA_OWNER}/{GITEA_REPO}/issues/{target_index}/labels",
                {"labels": plan["labels"]},
            )
            gitea.request(
                "PATCH",
                f"/repos/{GITEA_OWNER}/{GITEA_REPO}/issues/{target_index}",
                {
                    "title": str(source_issue.get("title") or ""),
                    "state": normalized_state(source_issue),
                    "body": rendered_body(source_issue, plan["label_names"]),
                },
            )
            print(f"Updated Gitea issue #{target_index} from GitHub #{number}.")
        else:
            # For manually edited copies, comments can still be added without touching issue fields.
            print(f"Left Gitea issue #{target['number']} unchanged for GitHub #{number} ({action}).")

        target_index = int(target["number"])
        for comment in plan["comment_additions"]:
            gitea.request(
                "POST",
                f"/repos/{GITEA_OWNER}/{GITEA_REPO}/issues/{target_index}/comments",
                {"body": comment_body(number, comment)},
            )
        if plan["comment_additions"]:
            print(f"Added {len(plan['comment_additions'])} comments to Gitea issue #{target_index}.")
        for comment_update in plan["comment_updates"]:
            copied = comment_update["target"]
            gitea.request(
                "PATCH",
                f"/repos/{GITEA_OWNER}/{GITEA_REPO}/issues/{target_index}/comments/{copied['id']}",
                {"body": comment_body(number, comment_update["source"])},
            )
        if plan["comment_updates"]:
            print(f"Updated {len(plan['comment_updates'])} comments on Gitea issue #{target_index}.")
        if plan_index == len(plans) or plan_index % 5 == 0:
            progress(f"Applied issue and comment changes ({plan_index}/{len(plans)} issues)...")
    print("Issue sync complete.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="harmonize-github-issues",
        description=(
            "Initial import and repeatable sync of etibger/agentic_tools GitHub issues "
            "to tibger01/agentic_tools on Gitea. Defaults to a read-only dry run."
        ),
        epilog=(
            "Use the same command for both the initial import and later syncs. "
            "Mapped issues are updated only when their Gitea fields still match the "
            "last sync fingerprint; manually edited issues are protected."
        ),
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--apply", action="store_true", help="write changes to Gitea (default is dry-run)"
    )
    args = parser.parse_args()
    try:
        return run(args.apply)
    except SyncError as exc:
        print(f"harmonize-github-issues: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("harmonize-github-issues: interrupted; rerun to resume safely", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
