"""Reject maintainer commits made under the wrong identity.

Maintainer commits must be authored and committed as the `brian-a-au`
GitHub account, using one of the emails in ALLOWED_MAINTAINER_EMAILS.
The check fails when:

- any author or committer email is an employer address (BLOCKED_DOMAINS), or
- the maintainer's name appears with an email outside the allowlist.

Commits from outside contributors and bots pass unchanged.

Usage:
    python3 scripts/check_commit_identity.py BASE..HEAD   # check a range
    python3 scripts/check_commit_identity.py --pending    # check the next commit
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Iterable

ALLOWED_MAINTAINER_EMAILS = frozenset(
    {
        "brian.a.au@gmail.com",
        "114970593+brian-a-au@users.noreply.github.com",
    }
)
MAINTAINER_NAMES = frozenset({"brian au", "brian-a-au", "bau"})
BLOCKED_DOMAINS = frozenset({"adobe.com"})


def identity_problem(role: str, name: str, email: str) -> str | None:
    """Return a description of what is wrong with one identity, else None."""
    normalized = email.strip().lower()
    domain = normalized.rpartition("@")[2]
    if domain in BLOCKED_DOMAINS:
        return f"{role} email {email!r} uses a blocked employer domain"
    if name.strip().lower() in MAINTAINER_NAMES and normalized not in ALLOWED_MAINTAINER_EMAILS:
        return f"{role} {name!r} <{email}> is not a brian-a-au email"
    return None


def problems_for(records: Iterable[tuple[str, str, str, str, str]]) -> list[str]:
    found = []
    for sha, author_name, author_email, committer_name, committer_email in records:
        for role, name, email in (
            ("author", author_name, author_email),
            ("committer", committer_name, committer_email),
        ):
            problem = identity_problem(role, name, email)
            if problem:
                found.append(f"{sha[:12]}: {problem}")
    return found


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


def range_records(rev_range: str) -> list[tuple[str, str, str, str, str]]:
    output = _git("log", "--format=%H%x1f%an%x1f%ae%x1f%cn%x1f%ce", rev_range)
    records = []
    for line in output.splitlines():
        fields = line.split("\x1f")
        if len(fields) == 5:
            records.append((fields[0], fields[1], fields[2], fields[3], fields[4]))
    return records


def _split_ident(ident: str) -> tuple[str, str]:
    name, _, rest = ident.partition(" <")
    return name, rest.partition(">")[0]


def pending_records() -> list[tuple[str, str, str, str, str]]:
    author = _split_ident(_git("var", "GIT_AUTHOR_IDENT"))
    committer = _split_ident(_git("var", "GIT_COMMITTER_IDENT"))
    return [("pending-commit", *author, *committer)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("rev_range", nargs="?", help="git revision range, e.g. BASE..HEAD")
    group.add_argument("--pending", action="store_true", help="check the next commit")
    args = parser.parse_args(argv)
    try:
        records = pending_records() if args.pending else range_records(args.rev_range)
    except subprocess.CalledProcessError as exc:
        print(f"commit identity error: git failed: {exc.stderr.strip()}", file=sys.stderr)
        return 2
    found = problems_for(records)
    if found:
        print("commit identity check failed:", file=sys.stderr)
        for problem in found:
            print(f"  {problem}", file=sys.stderr)
        print(
            "Commit as brian-a-au: git config user.email brian.a.au@gmail.com",
            file=sys.stderr,
        )
        return 1
    print(f"commit identity ok: {len(records)} commit(s) checked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
