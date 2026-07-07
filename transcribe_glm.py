# -*- coding: utf-8 -*-
"""
训练视频转写脚本 — 智谱 GLM ASR 版
流程：MP4 → 提取 WAV → 切片（25s/片）→ 并发调用 GLM ASR API → 合并文本 → 保存
API 限制：每次最多 30 秒，使用 25 秒切片留余量
"""

import os
import sys
import time
import json
import subprocess
import hashlib
import concurrent.futures
import requests

# ── 配置 ────────────────────────────────────────────────────────────────────
GLM_API_KEY  = "b07f119aaa41487a914d6b0d4dedd239.EAJ6rekpFjyZEWoA"
GLM_API_URL  = "https://open.bigmodel.cn/api/paas/v4/audio/transcriptions"
GLM_MODEL    = "glm-asr-2512"

TRAINING_DIR = r"c:/hrp/training"
OUTPUT_DIR   = r"c:/hrp/transcripts_glm"
AUDIO_DIR    = r"c:/hrp/audio_tmp"

FFMPEG  = r"c:/ffmpeg-master-latest-win64-gpl-shared/bin/ffmpeg.exe"
FFPROBE = r"c:/ffmpeg-master-latest-win64-gpl-shared/bin/ffprobe.exe"

SLICE_DURATION = 25   # 每片秒数，API 限制 30 秒，留 5 秒余量
MAX_WORKERS    = 5    # 并发切片数（避免过快被限流）
MAX_RETRIES    = 3    # 单片失败重试次数
# ─────────────────────────────────────────────────────────────────────────────


def ensure_dirs():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(AUDIO_DIR,  exist_ok=True)


def find_videos():
    videos = []
    for root, _, files in os.walk(TRAINING_DIR):
        for f in files:
            if f.lower().endswith(".mp4"):
                videos.append(os.path.join(root, f))
    return sorted(videos)


# ── 音频处理 ─────────────────────────────────────────────────────────────────

def _safe_name(mp4_path: str) -> str:
    h = hashlib.md5(mp4_path.encode("utf-8", errors="replace")).hexdigest()[:8]
    ascii_part = "".join(
        c for c in os.path.splitext(os.path.basename(mp4_path))[0]
        if c.isascii() and c not in r'\/:*?"<>|'
    ).strip().replace(" ", "_")[:30]
    return f"{ascii_part}_{h}" if ascii_part else h


def extract_audio(mp4_path: str) -> str:
    """提取为 16kHz 单声道 WAV"""
    os.makedirs(AUDIO_DIR, exist_ok=True)
    out_path = os.path.join(AUDIO_DIR, _safe_name(mp4_path) + ".wav")
    if os.path.exists(out_path):
        return out_path
    cmd = [FFMPEG, "-y", "-i", mp4_path, "-vn", "-ar", "16000", "-ac", "1",
           "-sample_fmt", "s16", out_path]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg 失败: {r.stderr.decode('utf-8','replace')[-300:]}")
    return out_path


def get_duration(wav_path: str) -> float:
    """获取 WAV 时长（秒）"""
    cmd = [FFPROBE, "-v", "error", "-show_entries", "format=duration",
           "-of", "default=noprint_wrappers=1:nokey=1", wav_path]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode == 0:
        try:
            return float(r.stdout.decode("utf-8", errors="replace").strip())
        except ValueError:
            pass
    return 0.0


def slice_audio(wav_path: str, slice_dir: str) -> list:
    """
    将 WAV 切片为 SLICE_DURATION 秒的子文件，返回有序切片路径列表
    """
    os.makedirs(slice_dir, exist_ok=True)
    duration = get_duration(wav_path)
    slices = []
    idx = 0
    start = 0.0
    while start < duration:
        out = os.path.join(slice_dir, f"slice_{idx:04d}.wav")
        cmd = [FFMPEG, "-y", "-i", wav_path,
               "-ss", str(start), "-t", str(SLICE_DURATION),
               "-ar", "16000", "-ac", "1", "-sample_fmt", "s16", out]
        r = subprocess.run(cmd, capture_output=True)
        if r.returncode != 0 or not os.path.exists(out):
            break
        slices.append(out)
        start += SLICE_DURATION
        idx += 1
    return slices


# ── GLM ASR API ───────────────────────────────────────────────────────────────

def transcribe_slice(slice_path: str) -> str:
    """调用 GLM ASR API 转写单个切片，失败自动重试"""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with open(slice_path, "rb") as f:
                resp = requests.post(
                    GLM_API_URL,
                    headers={"Authorization": f"Bearer {GLM_API_KEY}"},
                    files={"file": (os.path.basename(slice_path), f, "audio/wav")},
                    data={"model": GLM_MODEL, "stream": "false"},
                    timeout=60,
                )
            resp.raise_for_status()
            body = resp.json()
            if "text" in body:
                return body["text"]
            raise RuntimeError(f"API 返回无 text 字段: {body}")
        except Exception as e:
            if attempt == MAX_RETRIES:
                print(f"\n    [ERROR] 切片 {os.path.basename(slice_path)} 失败: {e}")
                return ""
            time.sleep(2 * attempt)
    return ""


def transcribe_audio(wav_path: str) -> str:
    """将整段 WAV 切片并发转写，返回合并文本"""
    base = os.path.splitext(os.path.basename(wav_path))[0]
    slice_dir = os.path.join(AUDIO_DIR, f"slices_{base}")

    print(f"  [切片] ", end="", flush=True)
    slices = slice_audio(wav_path, slice_dir)
    print(f"{len(slices)} 片", flush=True)

    results = [""] * len(slices)

    def _worker(args):
        idx, path = args
        text = transcribe_slice(path)
        print(f"  [转写] {idx+1}/{len(slices)} OK", end="\r", flush=True)
        return idx, text

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as exe:
        futs = {exe.submit(_worker, (i, p)): i for i, p in enumerate(slices)}
        for fut in concurrent.futures.as_completed(futs):
            idx, text = fut.result()
            results[idx] = text

    print()  # 换行
    return "".join(results)


# ── 路径工具 ──────────────────────────────────────────────────────────────────

def transcript_path(mp4_path: str) -> str:
    rel   = os.path.relpath(mp4_path, TRAINING_DIR)
    parts = rel.split(os.sep)
    # 如果视频在 TRAINING_DIR 外，relpath 会以 ".." 开头，此时用父目录名作为分类
    if parts[0] == "..":
        category = os.path.basename(os.path.dirname(mp4_path)) or "未分类"
    else:
        category = parts[0]
    filename  = os.path.splitext(parts[-1])[0] + ".txt"
    out_dir   = os.path.join(OUTPUT_DIR, category)
    os.makedirs(out_dir, exist_ok=True)
    return os.path.join(out_dir, filename)


def already_done(mp4_path: str) -> bool:
    txt = transcript_path(mp4_path)
    return os.path.exists(txt) and os.path.getsize(txt) > 10


# ── 主流程 ────────────────────────────────────────────────────────────────────

def process_video(mp4_path: str):
    name = os.path.basename(mp4_path)
    print(f"\n{'='*60}")
    print(f"处理: {name}")

    if already_done(mp4_path):
        print("  [跳过] 转写文件已存在")
        return

    print("  [1/3] 提取音频...")
    wav = extract_audio(mp4_path)
    dur = get_duration(wav)
    print(f"  时长: {dur:.1f}s  大小: {os.path.getsize(wav)//1024}KB")

    print("  [2/3] 切片并发转写...")
    text = transcribe_audio(wav)

    out = transcript_path(mp4_path)
    with open(out, "w", encoding="utf-8") as f:
        f.write(f"# {os.path.splitext(name)[0]}\n\n")
        f.write(text)
    print(f"  [3/3] 完成 → {out}  ({len(text)} 字)")


def main():
    ensure_dirs()
    videos = find_videos()
    print(f"共找到 {len(videos)} 个培训视频\n")

    failed = []
    for i, v in enumerate(videos, 1):
        print(f"[{i}/{len(videos)}]", end=" ")
        try:
            process_video(v)
        except Exception as e:
            print(f"\n  [ERROR] {e}")
            failed.append((v, str(e)))

    print(f"\n\n{'='*60}")
    print(f"完成！成功 {len(videos)-len(failed)}/{len(videos)}")
    if failed:
        print("\n失败列表:")
        for v, e in failed:
            print(f"  {os.path.basename(v)}: {e}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        ensure_dirs()
        process_video(sys.argv[1])
    else:
        main()
