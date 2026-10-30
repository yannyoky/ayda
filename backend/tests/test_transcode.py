"""ffmpeg reads uploads only with the demuxers our clients produce (audit V2)."""

import subprocess
from pathlib import Path

import pytest

from ayda.core import transcode


def tone(path: Path, *codec: str) -> Path:
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=duration=1", *codec, str(path)],
        check=True,
    )
    return path


async def test_voice_formats_from_clients_are_accepted(tmp_path: Path) -> None:
    for source in (
        tone(tmp_path / "chrome.webm", "-c:a", "libopus"),
        tone(tmp_path / "android.m4a", "-c:a", "aac"),
        tone(tmp_path / "firefox.ogg", "-c:a", "libopus"),
        tone(tmp_path / "old.mp3"),
    ):
        length = await transcode.transcode_voice(source, tmp_path / "out.m4a")
        assert 900 <= length <= 1200, source.name


async def test_playlists_are_never_opened(tmp_path: Path) -> None:
    # A playlist makes ffmpeg read other files, even ones on the server, into the output.
    other = tone(tmp_path / "other.m4a", "-c:a", "aac")
    concat = tmp_path / "voice.ffconcat"
    concat.write_text(f"ffconcat version 1.0\nfile '{other}'\n")
    playlist = tmp_path / "voice.m3u8"
    playlist.write_text(
        f"#EXTM3U\n#EXT-X-TARGETDURATION:1\n#EXTINF:1,\nfile://{other}\n#EXT-X-ENDLIST\n"
    )
    for source in (concat, playlist):
        with pytest.raises(transcode.InvalidMedia):
            await transcode.transcode_voice(source, tmp_path / "out.m4a")
        with pytest.raises(transcode.InvalidMedia):
            await transcode.transcode_video(source, tmp_path / "out.mp4")


async def test_audio_only_formats_are_not_videos(tmp_path: Path) -> None:
    source = tone(tmp_path / "song.mp3")
    with pytest.raises(transcode.InvalidMedia):
        await transcode.transcode_video_note(source, tmp_path / "out.mp4")
