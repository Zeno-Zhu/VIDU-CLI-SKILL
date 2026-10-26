# -*- coding: utf-8 -*-
"""回归：闲时无参考音色，仍必须保留台词与原生配音。"""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("vidu_check_prompts", ROOT / "scripts" / "vidu_check_prompts.py")
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)

ANCHOR = "中低音胸腔共鸣·3.3字/秒·句尾下压·轻微沙哑"
BLOCK = "【资产盘点】\n人物视觉资产：pn1,林桂芳=@\n\n【音色文字锁定】\n本组无参考音频，音色以下列设定为准。\n林桂芳：" + ANCHOR
DIALOGUE = [("林桂芳", "饭在锅里", "保持林桂芳的音色不变，声音压得很低。")]


class VoiceNativeDialogueTests(unittest.TestCase):
    def check(self, block, dialogue=None, mode="nopeak", cards=None):
        bads, warns = [], []
        checker.check_voice(block, DIALOGUE if dialogue is None else dialogue, mode, cards or {}, bads.append, warns.append)
        return bads, warns

    def test_nopeak_dialogue_with_text_lock_passes(self):
        bads, _ = self.check(BLOCK, cards={"林桂芳": ANCHOR})
        self.assertEqual(bads, [])

    def test_audio_asset_none_only_disables_binding_not_dialogue(self):
        block = BLOCK.replace("人物视觉资产：pn1,林桂芳=@", "人物视觉资产：pn1,林桂芳=@\n人物音色资产：无")
        bads, _ = self.check(block, cards={"林桂芳": ANCHOR})
        self.assertEqual(bads, [])

    def test_nopeak_vm_is_blocked_but_message_says_keep_dialogue(self):
        bads, _ = self.check(BLOCK + "\n人物音色资产：vm1,林桂芳音色=@")
        self.assertTrue(any("不能挂参考音色" in x for x in bads))
        self.assertTrue(any("台词照念" in x for x in bads))

    def test_text_lock_without_dialogue_blocks_suspected_deletion(self):
        bads, _ = self.check(BLOCK, dialogue=[])
        self.assertTrue(any("台词" in x and "删" in x for x in bads))

    def test_none_and_vm_contradiction_is_blocked(self):
        block = BLOCK.replace("人物视觉资产：pn1,林桂芳=@", "人物视觉资产：pn1,林桂芳=@\n人物音色资产：无\n人物音色资产：vm1,林桂芳音色=@")
        bads, _ = self.check(block)
        self.assertTrue(any("口径矛盾" in x for x in bads))

    def test_normal_with_reference_voice_and_dialogue_passes(self):
        block = "【资产盘点】\n人物视觉资产：pn1,林桂芳=@\n人物音色资产：vm1,林桂芳音色=@\n【音色严格规范】\n严格匹配参考音。"
        bads, _ = self.check(block, mode="normal")
        self.assertEqual(bads, [])


if __name__ == "__main__":
    unittest.main()
