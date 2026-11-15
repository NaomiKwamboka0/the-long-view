"""Give the tutorial video a different voice. Run this on your own computer (it needs internet).

    pip install edge-tts imageio-ffmpeg
    python scripts/tutorial_voice.py --episode teachers --voice en-KE-AsiliaNeural   # a Kenyan lady's voice
    python scripts/tutorial_voice.py --episode parents --voice en-KE-AsiliaNeural

It reads docs/tutorial/plan-<episode>.json (every line the guide says, and when), asks Microsoft
Edge's free read-aloud service to speak each line, puts each line at its time, and writes the new
sound into docs/guide/hatua-<episode>.mp4. The pictures are not changed, so the guide's lips,
which were drawn for the first voice, will fit the new voice only roughly.

edge-tts is an unofficial client for the Edge read-aloud voices. It is free and needs no
account, but Microsoft can change or stop it. The video in the repository uses the open
Kokoro voice (Apache 2.0), made offline by docs/tutorial/script.py.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def ffmpeg() -> str:
    found = shutil.which("ffmpeg")
    if found:
        return found
    import imageio_ffmpeg  # pip install imageio-ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def seconds(exe: str, path: Path) -> float:
    err = subprocess.run([exe, "-i", str(path)], capture_output=True, text=True).stderr
    h, m, s = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err).groups()
    return int(h) * 3600 + int(m) * 60 + float(s)


async def speak(lines: list[str], voice: str, rate: str, folder: Path) -> list[Path]:
    import edge_tts  # pip install edge-tts
    out = []
    for i, text in enumerate(lines):
        path = folder / f"{i:03d}.mp3"
        await edge_tts.Communicate(text, voice, rate=rate).save(str(path))
        out.append(path)
        print(f"  spoken {i + 1}/{len(lines)}: {text}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--voice", default="en-KE-AsiliaNeural")
    ap.add_argument("--rate", default="+0%", help="for example -5%% for a little slower")
    ap.add_argument("--episode", choices=["teachers", "parents"], default="teachers")
    args = ap.parse_args()
    args.video = REPO / "docs" / "guide" / f"hatua-{args.episode}.mp4"
    plan = json.loads((REPO / "docs" / "tutorial" / f"plan-{args.episode}.json").read_text(encoding="utf-8"))
    exe = ffmpeg()
    slots = []  # (text, when it starts, how long it may last)
    for sc in plan["scenes"]:
        for i, line in enumerate(sc["lines"]):
            end = sc["lines"][i + 1]["start"] if i + 1 < len(sc["lines"]) else sc["dur"] - 0.3
            slots.append((line["text"], sc["start"] + line["start"], end - line["start"] - 0.12))
    with tempfile.TemporaryDirectory(prefix="hatua-voice-") as tmp:
        clips = asyncio.run(speak([s[0] for s in slots], args.voice, args.rate, Path(tmp)))
        cmd, parts = [exe, "-loglevel", "error", "-y", "-i", str(args.video)], []
        for i, (clip, (_text, start, room)) in enumerate(zip(clips, slots)):
            cmd += ["-i", str(clip)]
            fast = min(1.35, max(1.0, seconds(exe, clip) / room))  # a slower voice is sped up a little to fit
            if fast > 1.12:
                print(f"  note: line {i + 1} is spoken {fast:.2f}x faster to fit its picture")
            parts.append(f"[{i + 1}:a]atempo={fast:.3f},adelay={int(start * 1000)}:all=1[a{i}]")
        mix = "".join(f"[a{i}]" for i in range(len(clips)))
        parts.append(f"{mix}amix=inputs={len(clips)}:normalize=0,apad=whole_dur={plan['total']}[voice]")
        out = args.video.with_name(args.video.stem + ".new.mp4")
        cmd += ["-filter_complex", ";".join(parts), "-map", "0:v", "-map", "[voice]", "-c:v", "copy",
                "-c:a", "aac", "-b:a", "128k", "-t", str(plan["total"]), "-movflags", "+faststart", str(out)]
        subprocess.run(cmd, check=True)
    out.replace(args.video)
    print(f"Done. {args.video} now speaks with {args.voice}.")


if __name__ == "__main__":
    main()
