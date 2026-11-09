# -*- coding: utf-8 -*-
"""绑定链路回归：分镜组表 + 资产清单 → pn 顺序。

跑法：python -m unittest tests.test_binding_chain -v
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


class BindingChainTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = self.tmp.name
        self.cfg = {
            "schema_version": "3.0", "project": "t",
            "profile": {"channel": "vidu-q4", "genre": "都市短剧", "aspect": "9:16",
                        "resolution": "1080p", "board_variant": "A", "audio_ref": "none",
                        "group_max_s": 16, "group_min_s": 4, "group_prefer_s": [12, 16],
                        "shot_max_s": 6, "shots_soft_max": 10, "max_images": 9,
                        "prompt_max_chars": 8000, "fixed_duration_s": None},
        }
        write(os.path.join(self.p, "项目配置.json"), json.dumps(self.cfg, ensure_ascii=False))
        inv = {"schema_version": "3.0", "style": {"main": "真人写实都市短剧", "texture": []},
               "assets": [
                   {"id": "CH01", "type": "character", "name": "林桂芳", "file": "林桂芳.png",
                    "status": "final", "board_variant": "A", "speaks": True,
                    "voice": {"mode": "text", "card": "音色-林桂芳.txt"},
                    "states": [{"name": "日常", "episodes": [1]}]},
                   {"id": "CH02", "type": "character", "name": "沈砚舟", "file": "沈砚舟.png",
                    "status": "final", "board_variant": "A", "speaks": True,
                    "voice": {"mode": "text", "card": "音色-沈砚舟.txt"},
                    "states": [{"name": "日常", "episodes": [1]}]},
                   {"id": "SC01", "type": "scene", "name": "老饭馆内景", "file": "老饭馆内景.png",
                    "status": "final", "subscenes": ["灶台区"]},
                   {"id": "PR01", "type": "prop", "name": "旧怀表", "file": "旧怀表.png",
                    "status": "final", "bound_to": "CH02"},
               ]}
        write(os.path.join(self.p, "00_剧本与提示词", "资产清单.json"),
              json.dumps(inv, ensure_ascii=False))
        tsv = ("组号\t分镜\t时长\t景别\t角度\t运镜\t功能\t内容\t台词\t站位\t出场资产\n"
               "1_1\tA1\t6\t中景\t平视\t固定\t叙事\t进门\t\tX\tCH01,CH02,SC01,PR01\n"
               "1_1\tA2\t8\t近景\t平视\t微推\t对白\t回头\t林桂芳：饭在锅里\tX\tCH01,CH02,SC01\n"
               "1_2\tA1\t8\t中景\t平视\t跟\t对白\t抬眼\t沈砚舟：妈，我回来了\tX\tCH01,CH02,SC01\n"
               "1_2\tA2\t6\t近景\t平视\t固定\t反应\t停手\t\tX\tCH01,SC01\n")
        self.sb = os.path.join(self.p, "00_剧本与提示词", "EP01", "分镜组", "EP01_分镜组.tsv")
        write(self.sb, tsv)

    def tearDown(self):
        self.tmp.cleanup()

    def run_script(self, name, *args):
        return subprocess.run([sys.executable, os.path.join(ROOT, "scripts", name)] + list(args),
                              capture_output=True, text=True, encoding="utf-8")

    def test_pn_order_and_bound_prop(self):
        out = os.path.join(self.p, "00_剧本与提示词", "EP01", "EP01_资产绑定.json")
        r = self.run_script("bind_assets.py", "--storyboard", self.sb,
                            "--assets", os.path.join(self.p, "00_剧本与提示词", "资产清单.json"),
                            "--episode", "1", "--out", out, "--freeze")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with open(out, encoding="utf-8") as f:
            d = json.load(f)
        g1 = d["groups"][0]
        self.assertEqual([(x["n"], x["name"]) for x in g1["pn"]],
                         [(1, "林桂芳"), (2, "沈砚舟"), (3, "老饭馆内景")])
        self.assertEqual([(x["n"], x["name"]) for x in d["groups"][1]["pn"]],
                         [(1, "林桂芳"), (2, "沈砚舟"), (3, "老饭馆内景")])

    def test_missing_asset_column_blocks(self):
        bad = os.path.join(self.p, "bad.tsv")
        write(bad, "组号\t分镜\t时长\t景别\t角度\t运镜\t功能\t内容\t台词\t站位\n"
                   "1_1\tA1\t12\t中景\t平视\t固定\t叙事\tx\t\tX\n")
        r = self.run_script("storyboard_check.py", bad, "--require-assets", "--quiet")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_unknown_asset_blocks(self):
        bad = os.path.join(self.p, "bad2.tsv")
        write(bad, "组号\t分镜\t时长\t景别\t角度\t运镜\t功能\t内容\t台词\t站位\t出场资产\n"
                   "1_1\tA1\t12\t中景\t平视\t固定\t叙事\tx\t\tX\tCH99,SC01\n")
        r = self.run_script("storyboard_check.py", bad,
                            "--assets", os.path.join(self.p, "00_剧本与提示词", "资产清单.json"),
                            "--require-assets", "--quiet")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
