"""verify_tier runs declared commands offline on a fake pinned archive and writes four consistent artifacts."""
import io
import json
import pathlib
import shutil
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import sync
import verify_tier


def archive(files):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for path, data in files.items():
            info = tarfile.TarInfo("repo-" + "1" * 40 + "/" + path)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


class VerifyTierTests(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.root_patch = patch.object(verify_tier, "ROOT", self.tmp)
        self.root_patch.start()
        (self.tmp / "plugins" / "demo" / "skills" / "alpha").mkdir(parents=True)
        (self.tmp / "plugins" / "demo" / "skills" / "alpha" / "SKILL.md").write_bytes(b"---\nname: alpha\n---\n")
        self.entry = {"name": "demo", "repo": "owner/repo", "ref": "v1", "sha": "1" * 40, "path": "skills", "skills": ["alpha"], "description": "d",
                      "maintainer": "m", "license": "MIT", "hosted_services": [],
                      "verification": {"selftest": ["python -c \"import sys; print('ok'); sys.exit(0)\""],
                                       "fixtures": [{"command": "python scripts/run.py", "cwd": "skills/alpha", "expect_exit": 0,
                                                     "expect_stdout_contains": "status\": \"PASS", "claim": "the example passes"}],
                                       "network": "none"}}
        self.files = {"LICENSE": b"MIT", "skills/alpha/SKILL.md": b"---\nname: alpha\n---\n",
                      "skills/alpha/scripts/run.py": b"import json; print(json.dumps({'status': 'PASS'}).replace(\"'\", '\"'))\n"}

    def tearDown(self):
        self.root_patch.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_verified_when_commands_match_and_tier_reads_back(self):
        with patch.object(sync, "fetch", return_value=archive(self.files)):
            result = verify_tier.verify_plugin(self.entry)
        self.assertEqual(result["state"], "VERIFIED")
        out = self.tmp / "verification" / "demo" / ("1" * 40)
        receipt = json.loads((out / "receipt.json").read_text())
        self.assertEqual(receipt["signature"], "UNSIGNED")
        self.assertEqual(receipt["network"], "none")
        for name in ("selftest.json", "fixtures.json", "manifest.json"):
            self.assertEqual(receipt["artifact_sha256"][name], verify_tier.sha256((out / name).read_bytes()))
        fixtures = json.loads((out / "fixtures.json").read_text())
        self.assertTrue(fixtures["passed"])
        self.assertEqual(fixtures["fixtures"][0]["cwd"], "skills/alpha")
        self.assertEqual(verify_tier.tier_of(self.entry)["tier"], "VERIFIED")
        (self.tmp / "plugins" / "demo" / "skills" / "alpha" / "SKILL.md").write_bytes(b"changed")
        self.assertEqual(verify_tier.tier_of(self.entry)["tier"], "BLOCKED")

    def test_failed_fixture_is_blocked_and_recorded(self):
        self.entry["verification"]["fixtures"][0]["expect_stdout_contains"] = "status\": \"FAIL"
        with patch.object(sync, "fetch", return_value=archive(self.files)):
            result = verify_tier.verify_plugin(self.entry)
        self.assertEqual(result["state"], "BLOCKED")
        self.assertEqual(verify_tier.tier_of(self.entry)["tier"], "BLOCKED")

    def test_listed_without_artifacts_and_selected_fetch_refused(self):
        self.assertEqual(verify_tier.tier_of(self.entry)["tier"], "LISTED")
        self.entry["fetch"] = "selected"
        with self.assertRaises(sync.SyncError):
            verify_tier.verify_plugin(self.entry)
        del self.entry["fetch"]
        self.entry["verification"]["network"] = "declared"
        with self.assertRaises(sync.SyncError):
            verify_tier.validate_verification(self.entry["verification"])

    def test_commands_run_without_network_or_credentials_in_env(self):
        self.files["probe.py"] = b"import os; print(os.environ.get('HTTPS_PROXY'), 'TOKEN' in ' '.join(os.environ))\n"
        self.entry["verification"]["selftest"] = ["python probe.py"]
        self.entry["verification"]["fixtures"] = []
        with patch.dict("os.environ", {"GITHUB_TOKEN": "secret-should-not-leak"}), patch.object(sync, "fetch", return_value=archive(self.files)):
            verify_tier.verify_plugin(self.entry)
        selftest = json.loads((self.tmp / "verification" / "demo" / ("1" * 40) / "selftest.json").read_text())
        self.assertEqual(selftest["commands"][0]["exit_code"], 0)
        # stdout digest of "http://127.0.0.1:9 False\n" proves the proxy pin and the absence of token variables
        self.assertEqual(selftest["commands"][0]["stdout_sha256"], verify_tier.sha256(b"http://127.0.0.1:9 False\n"))

    def test_archive_links_and_escapes_refused(self):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
            info = tarfile.TarInfo("repo-x/link"); info.type = tarfile.SYMTYPE; info.linkname = "/etc/passwd"
            tar.addfile(info)
        with self.assertRaises(sync.SyncError):
            verify_tier.extract_archive(buffer.getvalue(), self.tmp / "x")
        with self.assertRaises(sync.SyncError):
            verify_tier.extract_archive(archive({"../escape": b"x"}), self.tmp / "y")


if __name__ == "__main__":
    unittest.main()
