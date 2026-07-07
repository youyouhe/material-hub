"""
GLM ASR (Automatic Speech Recognition) Client.

Converts audio files (MP3/WAV) to text via Zhipu GLM API.
Ported from transcribe_glm.py, adapted for MaterialHub's pipeline.
"""

import os
import logging
import subprocess
import tempfile
from pathlib import Path

import requests

logger = logging.getLogger("materialhub.kb_asr")

# ── ASR configuration ──
ASR_ENABLED = os.getenv("ASR_ENABLED", "true").lower() == "true"
ASR_API_KEY = os.getenv("ASR_API_KEY", "b07f119aaa41487a914d6b0d4dedd239.EAJ6rekpFjyZEWoA")
ASR_API_URL = os.getenv("ASR_API_URL", "https://open.bigmodel.cn/api/paas/v4/audio/transcriptions")
ASR_MODEL = os.getenv("ASR_MODEL", "glm-asr-2512")

# FFmpeg for audio conversion
FFMPEG = os.getenv("FFMPEG_PATH", "ffmpeg")
FFPROBE = os.getenv("FFPROBE_PATH", "ffprobe")

SLICE_DURATION = 25   # seconds per slice (API limit: 30s)
MAX_RETRIES = 3
ASR_TIMEOUT = 60      # seconds per slice


def _is_audio(mime_type: str) -> bool:
    """Check if file is audio (MP3/WAV)."""
    audio_types = {
        "audio/mpeg", "audio/mp3", "audio/mpga", "audio/mpa",
        "audio/wav", "audio/wave", "audio/x-wav",
        "audio/ogg", "audio/flac", "audio/aac",
    }
    return mime_type.lower() in audio_types


def _convert_to_wav(file_path: str, output_dir: str = None) -> str:
    """Convert audio to 16kHz mono WAV using ffmpeg.

    Args:
        file_path: path to source audio file (MP3/WAV/etc.)
        output_dir: optional output directory (default: temp dir)

    Returns:
        Path to converted WAV file
    """
    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="materialhub_asr_")

    stem = Path(file_path).stem
    safe_name = "".join(c for c in stem if c.isascii() and c not in r'\/:*?"<>|')[:40]
    out_path = os.path.join(output_dir, f"{safe_name}.wav")

    if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
        return out_path

    cmd = [
        FFMPEG, "-y", "-i", file_path,
        "-vn", "-ar", "16000", "-ac", "1", "-sample_fmt", "s16",
        out_path,
    ]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        err = r.stderr.decode("utf-8", errors="replace")[-300:]
        raise RuntimeError(f"ffmpeg conversion failed: {err}")
    return out_path


def _get_duration(wav_path: str) -> float:
    """Get audio duration in seconds."""
    cmd = [
        FFPROBE, "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", wav_path,
    ]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode == 0:
        try:
            return float(r.stdout.decode("utf-8", errors="replace").strip())
        except ValueError:
            pass
    return 0.0


def _slice_audio(wav_path: str, slice_dir: str) -> list:
    """Slice WAV into SLICE_DURATION-second chunks."""
    os.makedirs(slice_dir, exist_ok=True)
    duration = _get_duration(wav_path)
    slices = []
    idx = 0
    start = 0.0
    while start < duration:
        out = os.path.join(slice_dir, f"slice_{idx:04d}.wav")
        cmd = [
            FFMPEG, "-y", "-i", wav_path,
            "-ss", str(start), "-t", str(SLICE_DURATION),
            "-ar", "16000", "-ac", "1", "-sample_fmt", "s16", out,
        ]
        r = subprocess.run(cmd, capture_output=True)
        if r.returncode != 0 or not os.path.exists(out):
            break
        slices.append(out)
        start += SLICE_DURATION
        idx += 1
    return slices


def _transcribe_slice(slice_path: str) -> str:
    """Call GLM ASR API for a single audio slice."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with open(slice_path, "rb") as f:
                resp = requests.post(
                    ASR_API_URL,
                    headers={"Authorization": f"Bearer {ASR_API_KEY}"},
                    files={"file": (os.path.basename(slice_path), f, "audio/wav")},
                    data={"model": ASR_MODEL, "stream": "false"},
                    timeout=ASR_TIMEOUT,
                )
            resp.raise_for_status()
            body = resp.json()
            if "text" in body:
                return body["text"]
            raise RuntimeError(f"API response missing 'text': {body}")
        except Exception as e:
            if attempt == MAX_RETRIES:
                logger.warning("ASR slice %s failed after %d attempts: %s",
                               os.path.basename(slice_path), MAX_RETRIES, e)
                return ""
            import time
            time.sleep(2 * attempt)
    return ""


def extract_audio_from_video(video_path: str, output_dir: str = None) -> str:
    """Extract audio track from video file as 16kHz mono WAV.

    Args:
        video_path: path to MP4/MKV/AVI/etc. video file
        output_dir: optional output directory

    Returns:
        Path to extracted WAV file
    """
    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="materialhub_video_")

    stem = Path(video_path).stem
    safe_name = "".join(c for c in stem if c.isascii() and c not in r'\/:*?"<>|')[:40]
    out_path = os.path.join(output_dir, f"{safe_name}_audio.wav")

    if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
        return out_path

    cmd = [
        FFMPEG, "-y", "-i", video_path,
        "-vn", "-ar", "16000", "-ac", "1", "-sample_fmt", "s16",
        out_path,
    ]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        err = r.stderr.decode("utf-8", errors="replace")[-300:]
        raise RuntimeError(f"ffmpeg video audio extraction failed: {err}")
    return out_path


def transcribe_audio(file_path: str) -> str:
    """Convert audio file to text via GLM ASR.

    Steps:
      1. Convert to 16kHz mono WAV (if not already)
      2. Slice into 25s chunks
      3. Transcribe each slice via API (sequential, not concurrent —
         to avoid overwhelming API)
      4. Merge all transcripts

    Args:
        file_path: path to MP3/WAV audio file

    Returns:
        Transcribed text string (empty on failure)
    """
    if not ASR_ENABLED:
        logger.info("ASR disabled (ASR_ENABLED=false)")
        return ""

    logger.info("Starting ASR transcription for: %s", os.path.basename(file_path))

    try:
        # 1. Convert to WAV
        wav_path = _convert_to_wav(file_path)
        duration = _get_duration(wav_path)
        size_kb = os.path.getsize(wav_path) // 1024
        logger.info("Audio: %.1fs, %dKB", duration, size_kb)

        # 2. Slice
        tmp_dir = tempfile.mkdtemp(prefix="asr_slices_")
        slices = _slice_audio(wav_path, tmp_dir)
        logger.info("Sliced into %d chunks", len(slices))

        if not slices:
            return ""

        # 3. Transcribe each slice
        texts = []
        for i, slice_path in enumerate(slices):
            text = _transcribe_slice(slice_path)
            if text:
                texts.append(text)
            logger.info("ASR slice %d/%d: %d chars",
                        i + 1, len(slices), len(text))

        # 4. Merge
        full_text = "".join(texts)
        logger.info("ASR complete: %d chars from %d slices",
                     len(full_text), len(slices))
        return full_text

    except Exception as e:
        logger.error("ASR transcription failed: %s", e)
        return ""
    finally:
        # Cleanup temp files
        import shutil
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass
