#!/usr/bin/env python3
"""Validate reviewed soak identity before network or package execution."""

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

REPOSITORY = "brian-a-au/sdr-grader"
MONITOR_FILES = [
    ".github/workflows/release-soak.yml",
    ".github/scripts/validate_release_soak_config.py",
    ".github/scripts/verify_release_soak_timeline.py",
]


def require(ok, message):
    if not ok:
        raise ValueError(message)


def epoch(value):
    require(
        isinstance(value, str) and re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", value),
        "UTC timestamp required",
    )
    return int(dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())


def validate(config):
    require(isinstance(config, dict), "config must be an object")
    require(
        type(config.get("schema_version")) is int and config.get("schema_version") == 1,
        "unsupported schema",
    )
    require(type(config.get("active")) is bool, "active must be boolean")
    if not config["active"]:
        return {}

    def identity(item, project, prefix):
        version = item["version"]
        require(re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version), "invalid version")
        require(item["tag"] == f"v{version}", "tag/version mismatch")
        for key in ("commit", "tag_object"):
            require(re.fullmatch(r"[0-9a-f]{40}", item[key]), f"invalid {key}")
        env = {f"{prefix}_{k.upper()}": item[k] for k in ("version", "tag", "commit", "tag_object")}
        for kind, name in (
            ("wheel", f"{project}-{version}-py3-none-any.whl"),
            ("sdist", f"{project}-{version}.tar.gz"),
            ("evidence", "release-artifacts.json" if prefix == "GRADER" else "SHA256SUMS"),
        ):
            asset = item[kind]
            require(asset["name"] == name, f"invalid {kind} filename")
            require(re.fullmatch(r"[0-9a-f]{64}", asset["sha256"]), f"invalid {kind} digest")
            env[f"{prefix}_{kind.upper()}"] = name
            digest_key = "SUMS" if prefix == "VISUALIZER" and kind == "evidence" else kind.upper()
            env[f"{prefix}_{digest_key}_SHA"] = asset["sha256"]
        return env

    env = identity(config["release"], "sdr_grader", "GRADER")
    companion = config["companion"]
    require(
        type(companion["applicable"]) is bool and bool(companion["reason"].strip()),
        "explicit companion applicability and reason required",
    )
    if companion["applicable"]:
        env.update(identity(companion["release"], "sdr_visualizer", "VISUALIZER"))
    require(re.fullmatch(r"[0-9a-f]{40}", config["monitor_commit"]), "invalid monitor commit")
    require(
        re.fullmatch(r"[a-z0-9][a-z0-9-]{7,63}", config["window_id"]), "invalid unique window id"
    )
    start, end = epoch(config["start_at"]), epoch(config["end_at"])
    require(end - start >= 172800, "window must be at least 48 hours")
    require(
        type(config["issue_number"]) is int and config["issue_number"] > 0,
        "invalid issue destination",
    )
    require(
        re.fullmatch(
            rf"https://github.com/{REPOSITORY}/issues/{config['issue_number']}#issuecomment-[1-9][0-9]*",
            config["start_evidence_url"],
        ),
        "start evidence must be a comment on the destination issue",
    )
    require(
        re.fullmatch(r"docs/releases/[a-zA-Z0-9._-]+\.md", config["readiness_record"]),
        "invalid readiness record",
    )
    env.update(
        SOAK_START_ISO=config["start_at"],
        SOAK_END_ISO=config["end_at"],
        SOAK_START_EPOCH=str(start),
        SOAK_END_EPOCH=str(end),
        SOAK_MARKER_PREFIX=f"sdr-grader-v{config['release']['version']}-{config['window_id']}",
        COMPANION_APPLICABLE=str(companion["applicable"]).lower(),
    )
    return env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=".github/release-soak/candidate.json")
    parser.add_argument("--env-output")
    parser.add_argument("--output")
    parser.add_argument("--verify-monitor", action="store_true")
    args = parser.parse_args()
    raw = Path(args.config).read_bytes()
    config = json.loads(raw)
    env = validate(config)
    if config["active"] and args.verify_monitor:
        require(os.environ.get("GITHUB_RUN_ATTEMPT", "1") == "1", "rerun attempts forbidden")
        for name in MONITOR_FILES:
            pinned = subprocess.check_output(["git", "show", f"{config['monitor_commit']}:{name}"])
            require(pinned == Path(name).read_bytes(), f"monitor bytes differ: {name}")
    env["SOAK_CONFIG_SHA"] = hashlib.sha256(raw).hexdigest()
    if args.env_output:
        with open(args.env_output, "a") as output:
            output.write("".join(f"{key}={value}\n" for key, value in env.items()))
    if args.output:
        with open(args.output, "a") as output:
            output.write(
                f"active={str(config['active']).lower()}\n"
                f"prefix={env.get('SOAK_MARKER_PREFIX', 'inactive')}\n"
            )


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, TypeError, AttributeError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"release soak config invalid: {exc}") from exc
