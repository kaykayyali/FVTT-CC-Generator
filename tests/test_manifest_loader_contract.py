from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
VALIDATOR = REPO_ROOT / "scripts" / "validate-module-json.py"


class ManifestLoaderContractTests(unittest.TestCase):
    def _run_validator(self, source: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as temp_dir:
            module_root = Path(temp_dir)
            manifest_path = module_root / "module.json"
            entry_path = module_root / "main.js"
            manifest_path.write_text(
                json.dumps(
                    {
                        "id": "loader-contract-probe",
                        "title": "Loader Contract Probe",
                        "description": "Regression fixture for Foundry script loading.",
                        "version": "1.0.0",
                        "authors": [{"name": "Test"}],
                        "compatibility": {"minimum": 12, "verified": 14},
                        "manifest": "https://example.com/module.json",
                        "download": "https://example.com/module.zip",
                        "scripts": ["main.js"],
                    }
                ),
                encoding="utf-8",
            )
            entry_path.write_text(source, encoding="utf-8")

            return subprocess.run(
                [sys.executable, str(VALIDATOR), str(manifest_path)],
                capture_output=True,
                text=True,
                timeout=10,
            )

    def test_classic_script_entry_rejects_static_module_syntax(self) -> None:
        rejected_sources = {
            "ordinary import": 'import { value } from "./dependency.js";\n',
            "compact import": 'import{value}from"./dependency.js";\n',
            "namespace import": 'import*as dependency from "./dependency.js";\n',
            "side-effect import": 'import "./dependency.js";\n',
            "import meta": "const here = import.meta.url;\n",
            "same-line import": '"use strict";import{value}from"./dependency.js";\n',
            "named export": "export{value};\n",
            "star export": 'export*from"./dependency.js";\n',
            "declaration export": "export const value = 1;\n",
            "same-line export": "const value = 1;export{value};\n",
            "regex brace before export": "const re = /{/; const value = 1; export{value};\n",
        }

        for label, source in rejected_sources.items():
            with self.subTest(label=label):
                result = self._run_validator(source)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("classic script", result.stdout.lower())
                self.assertIn("static import/export", result.stdout.lower())

    def test_classic_script_entry_allows_non_static_module_text(self) -> None:
        accepted_sources = {
            "dynamic import": 'async function load() { return import("./dependency.js"); }\n',
            "line comment": '// import { value } from "./dependency.js";\n',
            "block comment": '/*\nimport { value } from "./dependency.js";\n*/\n',
            "quoted text": 'const example = "export const value = 1";\n',
            "template literal": 'const example = `docs:\nimport { value } from "./dependency.js";`;\n',
            "regex containing export text": "const re = /;export{}/;\n",
        }

        for label, source in accepted_sources.items():
            with self.subTest(label=label):
                result = self._run_validator(source)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
