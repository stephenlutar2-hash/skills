"""Exercise the pinned vendored workbench offline; do not confuse this with app import."""
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "szl-science-skills"
SKILL = PLUGIN / "skills" / "szl-science-workbench"


class VendoredScienceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.project = pathlib.Path(self.temp.name) / "project"

    def tearDown(self):
        self.temp.cleanup()

    def execute(self, command, expected=0):
        result = subprocess.run([sys.executable, "-B", str(SKILL / "scripts" / "workbench.py"), command, str(self.project)],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, expected, result.stderr)
        return json.loads(result.stdout)

    def test_immutable_pin_and_generated_helpers_match(self):
        source = json.loads((PLUGIN / "SOURCE.json").read_text())
        entry = next(e for e in json.loads((ROOT / "registry.json").read_text())["plugins"] if e["name"] == "szl-science-skills")
        # The vendored pin must be the registry pin: a full 40-hex commit id and the tag it was resolved from.
        self.assertEqual(source["sha"], entry["sha"])
        self.assertEqual(source["ref"], entry["ref"])
        self.assertRegex(source["sha"], r"^[0-9a-f]{40}$")
        self.assertEqual(source["ref"], "v0.4.0")
        records = json.loads((SKILL / "references" / "implementations.json").read_text())
        self.assertEqual(len(records), 8)
        for record in records:
            raw = (SKILL / record["path"]).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), record["sha256"])
            if record["source"].startswith("skills/"):
                self.assertEqual(raw, (PLUGIN / record["source"]).read_bytes())

    def test_retained_capsule_and_expected_negative_results(self):
        self.execute("init")
        report = self.execute("run", 1)
        self.assertEqual(report["status"], "COMPLETED_WITH_FINDINGS")
        self.assertEqual(set(report["findings"]), {"dataset-check", "math-check", "paired-check"})
        self.assertFalse(report["scientific_truth_verified"])
        check = self.execute("check")
        self.assertEqual(check["capsule"]["integrity"], "MATCH")
        self.assertEqual(check["completion_record_binding"], "MATCH")
        self.assertEqual(check["changed_sources"], [])

    def test_changed_prediction_invalidates_dependent_conclusions(self):
        self.execute("init")
        self.execute("run", 1)
        path = self.project / "inputs" / "predictions.json"
        payload = json.loads(path.read_text())
        payload["probabilities"][0] = 0.3
        path.write_text(json.dumps(payload))
        report = self.execute("check", 1)
        self.assertEqual(report["changed_sources"], ["predictions"])
        self.assertTrue({"model-check", "kernel-check", "paired-check", "run", "conclusion"} <= set(report["recheck"]))
        self.assertEqual(report["capsule"]["integrity"], "MISMATCH")


if __name__ == "__main__":
    unittest.main()
