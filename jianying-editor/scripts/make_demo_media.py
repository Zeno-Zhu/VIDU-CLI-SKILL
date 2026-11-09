"""生成演示素材：assets/video.mp4、assets/audio.mp3。

为什么有这个脚本：上游 v1.7.0 随包带了 3 MB 的 video.mp4 和 128 KB 的 audio.mp3，
只为跑通 examples 和自检。本包把视频剔出去，需要时用 ffmpeg 现造一份，
体积不进技能包。examples 里的路径不用改，跑一次这个脚本就齐了。

用法：
    python scripts/make_demo_media.py            # 缺什么补什么
    python scripts/make_demo_media.py --force    # 全部重造
    python scripts/make_demo_media.py --out D:/tmp/media

退出码：0 成功或已存在｜2 缺 ffmpeg
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        print("[BLOCK] 找不到 ffmpeg。装一个再跑：https://ffmpeg.org/download.html")
        print("        Windows 可用：winget install Gyan.FFmpeg / choco install ffmpeg")
    return exe or ""


def build_video(out_path: str) -> bool:
    """10 秒 1280x720 测试片：彩条 + 移动方块 + 时间码，够 examples 演示剪辑用。"""
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i",
        "testsrc2=size=1280x720:rate=30:duration=10",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=10",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "28", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "96k", "-shortest",
        out_path,
    ]
    return _run(cmd, out_path)


def build_audio(out_path: str) -> bool:
    """10 秒简单音调，当作 BGM 占位。"""
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "sine=frequency=220:duration=10",
        "-af", "volume=0.25,afade=t=in:d=0.5,afade=t=out:st=9.5:d=0.5",
        "-c:a", "libmp3lame", "-b:a", "128k",
        out_path,
    ]
    return _run(cmd, out_path)


def _run(cmd: list[str], out_path: str) -> bool:
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if res.returncode != 0 or not os.path.exists(out_path):
        print("[BLOCK] 生成失败：%s" % out_path)
        tail = res.stderr.decode("utf-8", "replace").strip().splitlines()[-6:]
        for line in tail:
            print("        " + line)
        return False
    print("[OK] %s  %.1f KB" % (out_path, os.path.getsize(out_path) / 1024))
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="生成本地演示素材（不进技能包）")
    ap.add_argument("--out", default=os.path.join(SKILL_ROOT, "assets"), help="输出目录")
    ap.add_argument("--force", action="store_true", help="已存在也重造")
    a = ap.parse_args()

    if not _ffmpeg():
        return 2

    os.makedirs(a.out, exist_ok=True)
    ok = True
    targets = [("video.mp4", build_video), ("audio.mp3", build_audio)]
    for name, fn in targets:
        p = os.path.join(a.out, name)
        if os.path.exists(p) and not a.force:
            print("[SKIP] %s 已存在" % p)
            continue
        ok = fn(p) and ok

    if not ok:
        return 2
    print("\n演示素材已就绪：%s" % a.out)
    print("examples 里的 assets/video.mp4、assets/audio.mp3 现在能直接跑了。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
