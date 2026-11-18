# Copyright (C) 2024 The Android Open Source Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for init.py"""

import argparse
import io
import json
import os
import pathlib
import tempfile
import unittest
from typing import Generator
import zipfile

from init import (KleafBootstrap, _API_ENDPOINT_PREFIX,
                  _ARTIFACT_URL_FMT, _DEFAULT_BUILD_TARGET)

# pylint: disable=protected-access


def _get_branches() -> Generator[str, None, None]:
    url = _API_ENDPOINT_PREFIX + "branches.json"
    buf = io.BytesIO()
    KleafBootstrap._download(url, "branches", buf)
    buf.seek(0)
    json_obj = json.load(buf)
    yield from json_obj.get("branches", [])


def _get_supported_branches() -> Generator[str, None, None]:
    for branch in _get_branches():
        if not branch.startswith("aosp_kernel-common-android"):
            continue
        if branch == "aosp_kernel-common-android-mainline":
            yield branch
            continue
        android_release = branch.removeprefix(
            "aosp_kernel-common-android").split("-", maxsplit=1)[0]
        if not android_release.isdecimal():
            continue
        android_release = int(android_release)
        if android_release < 15:
            continue
        yield branch


class KleafBootstrapTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        print("INFO: Calculating supported branches")
        cls.supported_branches = list(_get_supported_branches())
        return super().setUpClass()

    def test_infer_build_id(self):
        for branch in self.supported_branches:
            with self.subTest(branch=branch):
                obj = KleafBootstrap(argparse.Namespace(
                    branch=branch,
                    build_target=_DEFAULT_BUILD_TARGET,
                    build_id=None,
                    ddk_workspace=None,
                    kleaf_repo=None,
                    local=None,
                    url_fmt=_ARTIFACT_URL_FMT,
                ), [])
                obj._set_build_id()
                print(f"For branch {branch}, checking {obj.build_id}")
                buf = io.BytesIO()
                obj._download_artifact("BUILD_INFO", buf)

    def test_run_with_help(self):
        for branch in self.supported_branches:
            with self.subTest(branch=branch):
                obj = KleafBootstrap(argparse.Namespace(
                    branch=branch,
                    build_target=_DEFAULT_BUILD_TARGET,
                    build_id=None,
                    ddk_workspace=pathlib.Path(os.getcwd()),
                    kleaf_repo=None,
                    local=None,
                    url_fmt=_ARTIFACT_URL_FMT,
                ), ["-h"])
                obj.run()


class KleafBootstrapLocalTest(unittest.TestCase):

    def test_flushes_init_ddk_zip_before_running(self):
        """Verifies init_ddk.zip is flushed to disk before python3 executes it.

        When the zip size mod 65536 falls in (0, 8192), the final chunk written
        by shutil.copyfileobj() stays buffered in NamedTemporaryFile unless
        flushed, truncating the ZIP End-of-Central-Directory record.
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            zip_path = tmp_path / "init_ddk.zip"
            target_size = 65536 + 585

            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as zf:
                zf.writestr("__main__.py", "import sys\nsys.exit(0)\n")
                zf.writestr("pad.bin", b"")
            overhead = zip_path.stat().st_size
            pad_len = target_size - overhead
            self.assertGreater(pad_len, 0)

            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as zf:
                zf.writestr("__main__.py", "import sys\nsys.exit(0)\n")
                zf.writestr("pad.bin", b"0" * pad_len)
            self.assertEqual(zip_path.stat().st_size, target_size)

            obj = KleafBootstrap(
                argparse.Namespace(
                    branch=None,
                    build_target=_DEFAULT_BUILD_TARGET,
                    build_id="12345",
                    ddk_workspace=tmp_path,
                    kleaf_repo=None,
                    local=False,
                    url_fmt=f"file://{tmp_path}/{{filename}}",
                ),
                [],
            )
            obj.run()


if __name__ == "__main__":
    unittest.main()
