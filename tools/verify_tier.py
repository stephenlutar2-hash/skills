#!/usr/bin/env python3
"""Verified tier, reference checker v0.1 (see docs/verified-tier.md).

  python -B tools/verify_tier.py run [--plugin NAME]   fetch each opted-in plugin's pinned archive, run its
                                                       declared self-tests and fixtures offline, write the four
                                                       artifacts under verification/<plugin>/<sha>/
  python -B tools/verify_tier.py check                 recompute the manifest of every vendored plugin and report
                                                       LISTED / VERIFIED / BLOCKED; exit 1 on BLOCKED

A plugin opts in with a "verification" block in its registry entry:

  "verification": {"selftest": ["python -B tools/selfcheck.py"], "fixtures": [{"command": "python -B scripts/run.py assets/example.json",
                   "cwd": "skills/x", "expect_exit": 0, "expect_stdout_contains": "\"status\": \"ABSTAIN\"", "claim": "..."}], "network": "none"}

VERIFIED means: the declared commands exited as declared on this runner at the pinned commit, the vendored
bytes match the manifest, and a receipt names who ran it and when. It does not mean the skill is correct,
safe, or reviewed by a human. Isolation in v0.1 is process-level (proxy variables pointed at a closed
port, no credentials in the environment), not a container; the receipt says so.
"""
from __future__ import annotations

import datetime
import getpass
import gzip
import hashlib
import io
import json
import os
import pathlib
import platform
import shlex
import subprocess
import sys
import tarfile
import tempfile
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import sync  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
CHECKER_VERSION = "0.1.0"
COMMAND_TIMEOUT = 600
TOTAL_BUDGET = 1200
MAX_OUTPUT = 4 * 1024 * 1024
OFFLINE_ENV = {"http_proxy": "http://127.0.0.1:9", "https_proxy": "http://127.0.0.1:9", "HTTP_PROXY": "http://127.0.0.1:9",
               "HTTPS_PROXY": "http://127.0.0.1:9", "ALL_PROXY": "http://127.0.0.1:9", "no_proxy": "", "NO_PROXY": "",
               "PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def validate_verification(block) -> None:
    if not isinstance(block, dict) or set(block) - {"selftest", "fixtures", "network"} or block.get("network") != "none":
        raise sync.SyncError("verification must be an object with selftest, fixtures and network: \"none\"")
    selftest = block.get("selftest", [])
    if not isinstance(selftest, list) or not selftest or any(not isinstance(c, str) or not c.strip() or len(c) > 512 for c in selftest):
        raise sync.SyncError("verification.selftest must be a non-empty list of command strings")
    fixtures = block.get("fixtures", [])
    if not isinstance(fixtures, list) or len(fixtures) > 100:
        raise sync.SyncError("verification.fixtures must be a list of at most 100 items")
    for f in fixtures:
        if not isinstance(f, dict) or set(f) - {"command", "cwd", "expect_exit", "expect_stdout_contains", "claim"}:
            raise sync.SyncError("fixture fields: command, cwd, expect_exit, expect_stdout_contains, claim")
        if not isinstance(f.get("command"), str) or not f["command"].strip() or len(f["command"]) > 512:
            raise sync.SyncError("fixture.command must be a command string")
        if not isinstance(f.get("claim"), str) or not f["claim"].strip():
            raise sync.SyncError("fixture.claim must state the SKILL.md sentence it supports")
        if not isinstance(f.get("expect_exit", 0), int) or isinstance(f.get("expect_exit", 0), bool):
            raise sync.SyncError("fixture.expect_exit must be an integer")
        if "cwd" in f:
            sync.safe_path(f["cwd"])
        if "expect_stdout_contains" in f and (not isinstance(f["expect_stdout_contains"], str) or not f["expect_stdout_contains"]):
            raise sync.SyncError("fixture.expect_stdout_contains must be a non-empty string")


def extract_archive(raw: bytes, destination: pathlib.Path) -> pathlib.Path:
    """Bounded, link-free extraction of a codeload-shaped archive; returns the single root directory."""
    if len(raw) > sync.MAX_DOWNLOAD:
        raise sync.SyncError("archive exceeds download budget")
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as compressed:
        unpacked = compressed.read(sync.MAX_EXPANDED + 1)
    if len(unpacked) > sync.MAX_EXPANDED:
        raise sync.SyncError("archive exceeds decompression budget")
    root, expanded = None, 0
    with tarfile.open(fileobj=io.BytesIO(unpacked), mode="r:") as archive:
        for count, member in enumerate(archive, 1):
            if count > sync.MAX_MEMBERS:
                raise sync.SyncError("archive exceeds member budget")
            name = member.name.rstrip("/") if member.isdir() else member.name
            sync.safe_path(name)
            first = name.split("/", 1)[0]
            root = root or first
            if first != root:
                raise sync.SyncError("archive has inconsistent root")
            if member.isdir():
                (destination / name).mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                raise sync.SyncError("archive links and special files are refused")
            expanded += member.size
            if expanded > sync.MAX_EXPANDED:
                raise sync.SyncError("archive exceeds expanded byte budget")
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            handle = archive.extractfile(member)
            target.write_bytes(handle.read())
            if member.mode & 0o111:
                target.chmod(0o755)
    if root is None:
        raise sync.SyncError("archive is empty")
    return destination / root


def run_command(command: str, cwd: pathlib.Path, timeout: float) -> dict:
    argv = shlex.split(command)
    if not argv:
        raise sync.SyncError("empty command")
    if argv[0] in ("python", "python3"):
        argv[0] = sys.executable
    env = {"PATH": os.environ.get("PATH", ""), "HOME": str(cwd), "TMPDIR": str(cwd / ".tmp"), **OFFLINE_ENV}
    (cwd / ".tmp").mkdir(exist_ok=True)
    started = time.monotonic()
    try:
        done = subprocess.run(argv, cwd=str(cwd), env=env, capture_output=True, timeout=timeout)
        exit_code, out, err, timed_out = done.returncode, done.stdout[:MAX_OUTPUT], done.stderr[:MAX_OUTPUT], False
    except subprocess.TimeoutExpired as expired:
        exit_code, out, err, timed_out = None, (expired.stdout or b"")[:MAX_OUTPUT], (expired.stderr or b"")[:MAX_OUTPUT], True
    except OSError as error:
        exit_code, out, err, timed_out = None, b"", str(error).encode(), False
    return {"command": command, "cwd": None, "exit_code": exit_code, "timed_out": timed_out,
            "stdout_sha256": sha256(out), "stdout_bytes": len(out), "stderr_sha256": sha256(err), "stderr_bytes": len(err),
            "stderr_tail": err[-400:].decode("utf-8", "replace"), "seconds": round(time.monotonic() - started, 3), "_stdout": out}


def manifest_for(plugin_dir: pathlib.Path) -> dict:
    files = []
    for path in sorted(p for p in plugin_dir.rglob("*") if p.is_file()):
        if path.is_symlink():
            raise sync.SyncError("vendored tree contains a link: %s" % path)
        data = path.read_bytes()
        files.append({"path": path.relative_to(plugin_dir).as_posix(), "size": len(data), "sha256": sha256(data)})
    return {"files": files, "root_sha256": sha256(canonical(files).encode("utf-8")), "file_count": len(files), "bytes": sum(f["size"] for f in files)}


def index_commit() -> str | None:
    try:
        return subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=30).stdout.strip() or None
    except (OSError, subprocess.TimeoutExpired):
        return None


def verify_plugin(entry: dict) -> dict:
    block = entry["verification"]
    validate_verification(block)
    if entry.get("fetch") == "selected":
        raise sync.SyncError("%s: the Verified tier needs the full pinned archive; selective fetch cannot run the publisher's self-tests" % entry["name"])
    out_dir = ROOT / "verification" / entry["name"] / entry["sha"]
    out_dir.mkdir(parents=True, exist_ok=True)
    budget_start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="verify-") as temporary:
        source = extract_archive(sync.fetch(entry["repo"], entry["sha"]), pathlib.Path(temporary))
        selftests = []
        for command in block["selftest"]:
            remaining = TOTAL_BUDGET - (time.monotonic() - budget_start)
            if remaining <= 0:
                raise sync.SyncError("verification exceeded the total time budget")
            record = run_command(command, source, min(COMMAND_TIMEOUT, remaining))
            record.pop("_stdout")
            record["cwd"] = "."
            selftests.append(record)
        fixtures = []
        for fixture in block.get("fixtures", []):
            cwd = source / fixture.get("cwd", ".")
            if not cwd.is_dir():
                fixtures.append({"command": fixture["command"], "cwd": fixture.get("cwd", "."), "claim": fixture["claim"], "exit_code": None,
                                 "expect_exit": fixture.get("expect_exit", 0), "matched": False, "reason": "cwd missing at pinned commit"})
                continue
            remaining = TOTAL_BUDGET - (time.monotonic() - budget_start)
            if remaining <= 0:
                raise sync.SyncError("verification exceeded the total time budget")
            record = run_command(fixture["command"], cwd, min(COMMAND_TIMEOUT, remaining))
            stdout = record.pop("_stdout")
            record["cwd"] = fixture.get("cwd", ".")
            record["claim"] = fixture["claim"]
            record["expect_exit"] = fixture.get("expect_exit", 0)
            matched = record["exit_code"] == record["expect_exit"]
            if "expect_stdout_contains" in fixture:
                record["expect_stdout_contains"] = fixture["expect_stdout_contains"]
                matched = matched and fixture["expect_stdout_contains"].encode("utf-8") in stdout
            record["matched"] = matched
            fixtures.append(record)
    selftest_doc = {"plugin": entry["name"], "sha": entry["sha"], "repo": entry["repo"], "ref": entry["ref"], "commands": selftests,
                    "passed": all(r["exit_code"] == 0 for r in selftests)}
    fixtures_doc = {"plugin": entry["name"], "sha": entry["sha"], "fixtures": fixtures, "declared": len(fixtures),
                    "matched": sum(1 for f in fixtures if f["matched"]), "passed": all(f["matched"] for f in fixtures)}
    manifest_doc = {"plugin": entry["name"], "sha": entry["sha"], **manifest_for(ROOT / "plugins" / entry["name"])}
    for name, doc in (("selftest.json", selftest_doc), ("fixtures.json", fixtures_doc), ("manifest.json", manifest_doc)):
        (out_dir / name).write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    digests = {name: sha256((out_dir / name).read_bytes()) for name in ("selftest.json", "fixtures.json", "manifest.json")}
    state = "VERIFIED" if selftest_doc["passed"] and fixtures_doc["passed"] else "BLOCKED"
    receipt = {"plugin": entry["name"], "sha": entry["sha"], "state": state, "checker": "tools/verify_tier.py", "checker_version": CHECKER_VERSION,
               "index_commit": index_commit(), "runner": {"identity": os.environ.get("GITHUB_ACTOR") or getpass.getuser(),
               "host": os.environ.get("RUNNER_NAME") or platform.node(), "platform": platform.platform(), "python": platform.python_version(),
               "ci": bool(os.environ.get("GITHUB_ACTIONS"))}, "network": "none",
               "isolation": "process environment: proxy variables pointed at a closed port, no credentials, writable temp only; not a container",
               "utc": utc_now(), "artifact_sha256": digests, "signature": "UNSIGNED",
               "means": "declared commands exited as declared on this runner at the pinned commit and the vendored bytes match the manifest",
               "does_not_mean": "scientific correctness, safety on your data, publisher identity, triggering quality, or human review"}
    (out_dir / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"plugin": entry["name"], "state": state, "selftest_passed": selftest_doc["passed"], "fixtures": "%d/%d" % (fixtures_doc["matched"], fixtures_doc["declared"]),
            "receipt_sha256": sha256((out_dir / "receipt.json").read_bytes())}


def tier_of(entry: dict, plugins_root: pathlib.Path | None = None) -> dict:
    """LISTED, VERIFIED <receipt digest> or BLOCKED for the pinned sha, from the committed artifacts."""
    plugins_root = plugins_root or (ROOT / "plugins")
    out_dir = ROOT / "verification" / entry["name"] / entry["sha"]
    receipt_path = out_dir / "receipt.json"
    if not receipt_path.is_file():
        return {"plugin": entry["name"], "tier": "LISTED", "reason": "no verification artifacts for the pinned commit"}
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
        for name in ("selftest.json", "fixtures.json", "manifest.json"):
            if receipt["artifact_sha256"][name] != sha256((out_dir / name).read_bytes()):
                return {"plugin": entry["name"], "tier": "BLOCKED", "reason": "%s does not match the receipt" % name}
    except (OSError, ValueError, KeyError) as error:
        return {"plugin": entry["name"], "tier": "BLOCKED", "reason": "unreadable verification artifacts: %s" % error}
    current = manifest_for(plugins_root / entry["name"])
    if current["root_sha256"] != manifest.get("root_sha256"):
        return {"plugin": entry["name"], "tier": "BLOCKED", "reason": "vendored bytes differ from the verified manifest"}
    if receipt.get("state") != "VERIFIED":
        return {"plugin": entry["name"], "tier": "BLOCKED", "reason": "the recorded check did not pass"}
    return {"plugin": entry["name"], "tier": "VERIFIED", "receipt_sha256": sha256(receipt_path.read_bytes()), "utc": receipt.get("utc")}


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in ("run", "check"):
        print(__doc__)
        return 2
    registry = sync.read_json((ROOT / "registry.json").read_bytes())
    sync.validate_registry(registry)
    if argv[0] == "check":
        rows = [tier_of(e) for e in registry["plugins"]]
        for row in rows:
            print("%-32s %-9s %s" % (row["plugin"], row["tier"], row.get("receipt_sha256", row.get("reason", ""))[:64]))
        return 1 if any(r["tier"] == "BLOCKED" for r in rows) else 0
    only = argv[2] if len(argv) >= 3 and argv[1] == "--plugin" else None
    results = []
    for entry in registry["plugins"]:
        if "verification" not in entry or (only and entry["name"] != only):
            continue
        results.append(verify_plugin(entry))
        print(json.dumps(results[-1]))
    if not results:
        print("no plugin opted in to verification" + (" or no plugin named %s" % only if only else ""))
        return 2
    return 0 if all(r["state"] == "VERIFIED" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
