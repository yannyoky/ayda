"""Re-encoding voice messages and video circles with ffmpeg (ADR 0019).

Every upload is decoded and written anew: voice as mono AAC in M4A, a circle as a square
480x480 H.264 + AAC MP4. Browsers, iOS and Android play both. Metadata of the original
(device, app, location) is dropped.
"""

import asyncio
import json
from pathlib import Path

MAX_VOICE_SECONDS = 300
MAX_VIDEO_NOTE_SECONDS = 60
VIDEO_NOTE_SIDE = 480
TIMEOUT_S = 120


class InvalidMedia(ValueError):
    pass


async def _run(*args: str) -> bytes:
    process = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
    )
    try:
        out, _ = await asyncio.wait_for(process.communicate(), TIMEOUT_S)
    except TimeoutError:
        process.kill()
        await process.wait()
        raise InvalidMedia("timeout") from None
    if process.returncode != 0:
        raise InvalidMedia(f"{args[0]} exit {process.returncode}")
    return out


async def duration_ms(path: Path) -> int:
    out = await _run(
        "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)
    )
    try:
        seconds = float(json.loads(out)["format"]["duration"])
    except (KeyError, ValueError, TypeError):
        raise InvalidMedia("no duration") from None
    return round(seconds * 1000)


async def transcode_voice(source: Path, target: Path) -> int:
    """Write `target` as M4A (AAC, mono, ~32 kbit/s), at most 5 minutes; returns its length."""
    await _run(
        "ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(source),
        "-t", str(MAX_VOICE_SECONDS), "-vn", "-sn", "-dn", "-map_metadata", "-1",
        "-ac", "1", "-ar", "24000", "-c:a", "aac", "-b:a", "32k",
        "-movflags", "+faststart", "-f", "mp4", str(target),
    )  # fmt: skip
    length = await duration_ms(target)
    if length <= 0:
        raise InvalidMedia("empty")
    return length


async def transcode_video_note(source: Path, target: Path) -> int:
    """Write `target` as a square MP4 (H.264 ~600 kbit/s, AAC mono), at most 60 seconds,
    cut from the middle of the frame; returns its length. Rotation is applied first."""
    side = VIDEO_NOTE_SIDE
    crop = f"crop='min(iw,ih)':'min(iw,ih)',scale={side}:{side},setsar=1"
    await _run(
        "ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(source),
        "-t", str(MAX_VIDEO_NOTE_SECONDS), "-map", "0:v:0", "-map", "0:a:0?",
        "-sn", "-dn", "-map_metadata", "-1", "-map_chapters", "-1",
        "-vf", crop, "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
        "-maxrate", "700k", "-bufsize", "1400k", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ac", "1", "-b:a", "48k",
        "-movflags", "+faststart", "-f", "mp4", str(target),
    )  # fmt: skip
    length = await duration_ms(target)
    if length <= 0:
        raise InvalidMedia("empty")
    return length
