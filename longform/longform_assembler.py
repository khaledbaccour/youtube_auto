"""
Longform baby niche video assembler.
- Generates continuous TTS audio via Cartesia Sonic with emotion
- Assembles video with subtle Ken Burns zoom + hard cuts + continuous audio
"""

import os
import sys
import json
import re
import struct
import requests
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

# Cartesia config
CARTESIA_API_KEY = os.environ.get("CARTESIA_API_KEY", "")
LONGFORM_VOICE_ID = os.environ.get("LONGFORM_VOICE_ID", "")
CARTESIA_MODEL = "sonic-3"
CARTESIA_SAMPLE_RATE = 44100

# Ken Burns config — subtle, just enough to keep attention
ZOOM_RATIO = 1.05  # 5% zoom over each scene duration


def _cartesia_tts(text, output_path, emotion="content"):
    """Generate audio via Cartesia Sonic API with emotion. Returns True on success."""
    headers = {
        "X-API-Key": CARTESIA_API_KEY,
        "Cartesia-Version": "2025-04-16",
        "Content-Type": "application/json",
    }
    payload = {
        "model_id": CARTESIA_MODEL,
        "transcript": text,
        "voice": {"mode": "id", "id": LONGFORM_VOICE_ID},
        "output_format": {
            "container": "wav",
            "encoding": "pcm_f32le",
            "sample_rate": CARTESIA_SAMPLE_RATE,
        },
        "language": "en",
        "generation_config": {
            "speed": 0.9,
            "emotion": "curiosity:high",
        },
    }

    resp = requests.post(
        "https://api.cartesia.ai/tts/bytes",
        json=payload,
        headers=headers,
        timeout=120,
    )

    if resp.status_code == 200 and len(resp.content) > 1000:
        with open(output_path, "wb") as f:
            f.write(resp.content)
        return True

    print(f"  Cartesia API error: {resp.status_code} - {resp.text[:300]}")
    return False


def _get_wav_duration(path):
    """Get duration of a WAV file in seconds."""
    try:
        file_size = os.path.getsize(path)
        with open(path, "rb") as f:
            f.read(4)  # RIFF
            f.read(4)  # size
            f.read(4)  # WAVE
            channels = 1
            sample_rate = CARTESIA_SAMPLE_RATE
            bits_per_sample = 32
            while True:
                chunk_id = f.read(4)
                if len(chunk_id) < 4:
                    break
                chunk_size = struct.unpack("<I", f.read(4))[0]
                if chunk_id == b"fmt ":
                    fmt_data = f.read(chunk_size)
                    channels = struct.unpack("<H", fmt_data[2:4])[0]
                    sample_rate = struct.unpack("<I", fmt_data[4:8])[0]
                    bits_per_sample = struct.unpack("<H", fmt_data[14:16])[0]
                elif chunk_id == b"data":
                    bytes_per_sample = bits_per_sample // 8
                    if chunk_size >= 0xFFFFFFFF - 1:
                        actual_data_size = file_size - f.tell()
                    else:
                        actual_data_size = chunk_size
                    num_samples = actual_data_size // (bytes_per_sample * channels)
                    return num_samples / sample_rate
                else:
                    f.seek(chunk_size, 1)
    except Exception as e:
        print(f"  WAV duration error: {e}")
    return os.path.getsize(path) / (CARTESIA_SAMPLE_RATE * 4)


def generate_tts(full_narration, output_path=None):
    """Generate continuous TTS audio from the full narration.

    Chunks at sentence boundaries if text is too long for a single API call.
    Returns total duration in seconds, or None on failure.
    """
    if output_path is None:
        output_path = os.path.join(OUTPUT_DIR, "audio", "full_narration.wav")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Clean pause markers — replace ... with comma for natural pauses
    clean_text = full_narration.replace("...", ", ").strip()
    clean_text = re.sub(r'\s+', ' ', clean_text)

    if not clean_text:
        print("  ERROR: Empty narration text.")
        return None

    print(f"  Generating TTS audio ({len(clean_text)} chars, {len(clean_text.split())} words)...")
    print(f"  Voice: {LONGFORM_VOICE_ID}")

    # Try single call first
    success = _cartesia_tts(clean_text, output_path)
    if success:
        duration = _get_wav_duration(output_path)
        print(f"  Audio generated: {duration:.1f}s (single call)")
        return duration

    # Chunk at sentence boundaries (~2000 chars per chunk)
    print("  Single call failed, chunking at sentence boundaries...")
    return _generate_chunked(clean_text, output_path)


def _generate_chunked(text, output_path, max_chunk_chars=2000):
    """Split text at sentence boundaries and concatenate audio chunks."""
    import soundfile as sf

    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks = []
    current = ""

    for sentence in sentences:
        if len(current) + len(sentence) > max_chunk_chars and current:
            chunks.append(current.strip())
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        chunks.append(current.strip())

    print(f"  Split into {len(chunks)} chunks...")

    all_samples = []
    sample_rate = CARTESIA_SAMPLE_RATE

    for i, chunk in enumerate(chunks):
        chunk_path = output_path + f".chunk{i}.wav"
        print(f"  Chunk {i+1}/{len(chunks)} ({len(chunk)} chars)...")
        success = _cartesia_tts(chunk, chunk_path)
        if not success:
            for j in range(i):
                p = output_path + f".chunk{j}.wav"
                if os.path.exists(p):
                    os.remove(p)
            return None

        data, sr = sf.read(chunk_path)
        sample_rate = sr
        all_samples.append(data)

        # Tiny silence between chunks (100ms)
        if i < len(chunks) - 1:
            silence = np.zeros(int(sr * 0.1), dtype=data.dtype)
            all_samples.append(silence)

        os.remove(chunk_path)

    combined = np.concatenate(all_samples)
    sf.write(output_path, combined, sample_rate)

    duration = len(combined) / sample_rate
    print(f"  Chunked audio generated: {duration:.1f}s ({len(chunks)} chunks)")
    return duration


def calculate_scene_durations(scenes, total_duration):
    """Calculate each scene's duration proportional to its narration length."""
    char_counts = [len(s.get("narration", "").replace("...", "")) for s in scenes]
    total_chars = sum(char_counts)
    if total_chars == 0:
        return [total_duration / len(scenes)] * len(scenes)
    return [(c / total_chars) * total_duration for c in char_counts]


def assemble_video(scene_durations, audio_path, output_path=None):
    """Assemble final video using ffmpeg: Ken Burns zoompan on each image + continuous audio.

    Uses ffmpeg's zoompan filter (hardware-optimized) instead of frame-by-frame Python rendering.
    """
    import subprocess
    import tempfile

    if output_path is None:
        output_path = os.path.join(OUTPUT_DIR, "video.mp4")
    os.makedirs(os.path.dirname(output_path) or OUTPUT_DIR, exist_ok=True)

    images_dir = os.path.join(OUTPUT_DIR, "images")
    temp_dir = os.path.join(OUTPUT_DIR, "temp_clips")
    os.makedirs(temp_dir, exist_ok=True)

    clip_paths = []

    for i, duration in enumerate(scene_durations):
        scene_num = i + 1
        img_path = os.path.join(images_dir, f"scene_{scene_num:03d}.png")
        clip_path = os.path.join(temp_dir, f"clip_{scene_num:03d}.mp4")

        if not os.path.exists(img_path):
            print(f"  WARNING: Missing {img_path}, skipping")
            continue

        total_frames = int(duration * 30)
        if total_frames < 1:
            total_frames = 1

        # zoompan: subtle 5% zoom over scene duration, centered
        # accumulative zoom: each frame adds increment to previous zoom level
        zoom_increment = (ZOOM_RATIO - 1.0) / total_frames if total_frames > 0 else 0

        cmd = [
            "ffmpeg", "-y",
            "-i", img_path,
            "-vf", (
                f"zoompan=z='min(zoom+{zoom_increment:.8f},{ZOOM_RATIO})':"
                f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"d={total_frames}:s=1920x1080:fps=30,"
                f"format=yuv420p"
            ),
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-an", clip_path,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            print(f"  ERROR scene {scene_num}: {result.stderr[-200:]}")
            continue

        clip_paths.append(clip_path)

        if scene_num % 10 == 0:
            print(f"  Rendered {scene_num}/{len(scene_durations)} scenes...")

    print(f"  All {len(clip_paths)} clips rendered. Concatenating with audio...")

    # Write ffmpeg concat list
    concat_list = os.path.join(temp_dir, "concat.txt")
    with open(concat_list, "w") as f:
        for cp in clip_paths:
            f.write(f"file '{cp.replace(os.sep, '/')}'\n")

    # Concat all clips + add audio
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", concat_list,
        "-i", audio_path,
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        output_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        print(f"  Concat error: {result.stderr[-300:]}")
        return None

    # Cleanup temp clips
    for cp in clip_paths:
        os.remove(cp)
    os.remove(concat_list)
    os.rmdir(temp_dir)

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"  Video saved: {output_path} ({size_mb:.1f} MB)")
    return output_path


def run():
    """Full pipeline: TTS + video assembly."""
    # Load script
    script_path = os.path.join(OUTPUT_DIR, "script.json")
    with open(script_path, "r", encoding="utf-8") as f:
        script = json.load(f)

    full_narration = script["full_narration"]
    scenes = script["scenes"]
    print(f"  Script: {len(scenes)} scenes, {len(full_narration.split())} words")

    # Step 1: Generate TTS
    audio_path = os.path.join(OUTPUT_DIR, "audio", "full_narration.wav")
    if os.path.exists(audio_path):
        duration = _get_wav_duration(audio_path)
        print(f"  Audio already exists: {duration:.1f}s — skipping TTS generation")
    else:
        duration = generate_tts(full_narration, audio_path)
        if duration is None:
            print("  FATAL: TTS generation failed.")
            return

    # Step 2: Calculate proportional scene durations
    scene_durations = calculate_scene_durations(scenes, duration)
    print(f"  Scene durations: min={min(scene_durations):.1f}s, max={max(scene_durations):.1f}s, total={sum(scene_durations):.1f}s")

    # Step 3: Assemble video
    output_path = os.path.join(OUTPUT_DIR, "video.mp4")
    assemble_video(scene_durations, audio_path, output_path)


if __name__ == "__main__":
    run()
