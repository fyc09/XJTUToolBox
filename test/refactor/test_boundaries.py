import subprocess
import sys
import unittest

TEST_DOMAIN = "core"

from scripts.check_architecture import check, violations


class BoundaryTest(unittest.TestCase):
    def test_migrated_code_obeys_layer_contract(self):
        self.assertEqual([], check())

    def test_type_checking_imports_cannot_hide_qt(self):
        self.assertTrue(
            violations(
                "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n from PySide6 import QtCore",
                "services",
            )
        )

    def test_api_cannot_import_progress_contract(self):
        self.assertTrue(
            violations("from xjtutoolbox.contracts.tasks import Progress", "api")
        )

    def test_dynamic_import_cannot_hide_forbidden_dependency(self):
        self.assertTrue(
            violations(
                "import importlib\nimportlib.import_module('PyQt5.QtCore')", "services"
            )
        )

    def test_frontends_cannot_reach_raw_transport(self):
        for layer in ("gui", "cli"):
            with self.subTest(layer=layer):
                self.assertTrue(violations("import requests", layer))

    def test_importlib_alias_cannot_hide_transport(self):
        self.assertTrue(
            violations(
                "import importlib as loader\nloader.import_module('requests')", "gui"
            )
        )

    def test_relative_import_cannot_hide_api_from_frontend(self):
        self.assertTrue(violations("from .. import api", "gui"))

    def test_cli_and_real_core_import_with_all_qt_imports_blocked(self):
        program = """
import importlib.abc, sys, tempfile
from pathlib import Path
class BlockQt(importlib.abc.MetaPathFinder):
 def find_spec(self, fullname, path=None, target=None):
  if fullname.startswith(('PyQt', 'PySide', 'qfluent', 'qframeless')):
   raise RuntimeError('Qt dependency: '+fullname)
sys.meta_path.insert(0, BlockQt())
from xjtutoolbox.bootstrap import build_application
from xjtutoolbox.cli.main import main
with tempfile.TemporaryDirectory() as directory:
 application=build_application(Path(directory))
 assert main(['accounts','list','--json'],application=application)==0
 application.close()
"""
        result = subprocess.run(
            [sys.executable, "-c", program], capture_output=True, text=True, timeout=20
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("[]", result.stdout.strip())
