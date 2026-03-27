"""
Shorts TTS engine — Cartesia Sonic with native word-level timestamps via SSE.
Falls back to Kokoro TTS if Cartesia fails.
"""

import os
import re
import json
import struct
import base64
import requests
import numpy as np

from shorts_config import (
    CARTESIA_API_KEY, CARTESIA_MODEL, CARTESIA_SAMPLE_RATE,
    SHORTS_VOICE_ID, KOKORO_MODEL_PATH, KOKORO_VOICES_PATH,
    KOKORO_VOICE, KOKORO_SPEED, OUTPUT_DIR,
)


def generate_narration_with_timestamps(text, output_path=None):
    """Generate TTS audio with precise word-level timestamps.

    Returns: (duration_s, word_timestamps)
        word_timestamps: [{"word": "Why", "start_s": 0.0, "end_s": 0.07}, ...]
    """
    if output_path is None:
        output_path = os.path.join(OUTPUT_DIR, "audio", "narration.wav")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    clean = text.replace("...", ", ").strip()
    clean = re.sub(r'\s+', ' ', clean)

    if not clean:
        print("  ERROR: Empty narration text.")
        return None, None

    print(f"  Generating narration with timestamps ({len(clean)} chars)...")

    # Try Cartesia SSE with timestamps
    duration, timestamps = _cartesia_sse_with_timestamps(clean, output_path)
    if duration and timestamps:
        print(f"  Narration: {duration:.1f}s, {len(timestamps)} words timestamped via Cartesia SSE")
        return duration, timestamps

    # Fallback: Cartesia bytes endpoint + estimated timestamps
    print("  SSE failed, trying Cartesia bytes endpoint...")
    duration = _cartesia_bytes(clean, output_path)
    if duration:
        timestamps = _estimate_word_timestamps(clean, duration)
        print(f"  Narration: {duration:.1f}s, {len(timestamps)} words (estimated) via Cartesia bytes")
        return duration, timestamps

    # Fallback: Kokoro
    print("  Cartesia failed, trying Kokoro fallback...")
    duration, timestamps = _kokoro_fallback(text, output_path)
    if duration:
        print(f"  Narration: {duration:.1f}s via Kokoro fallback")
    return duration, timestamps


def _cartesia_sse_with_timestamps(text, output_path):
    """Cartesia SSE streaming endpoint with native word timestamps."""
    headers = {
        "X-API-Key": CARTESIA_API_KEY,
        "Cartesia-Version": "2025-04-16",
        "Content-Type": "application/json",
    }
    payload = {
        "model_id": CARTESIA_MODEL,
        "transcript": text,
        "voice": {"mode": "id", "id": SHORTS_VOICE_ID},
        "output_format": {
            "container": "raw",
            "encoding": "pcm_f32le",
            "sample_rate": CARTESIA_SAMPLE_RATE,
        },
        "language": "en",
        "add_timestamps": True,
    }

    try:
        resp = requests.post(
            "https://api.cartesia.ai/tts/sse",
            json=payload,
            headers=headers,
            timeout=120,
            stream=True,
        )

        if resp.status_code != 200:
            print(f"  Cartesia SSE error: {resp.status_code} - {resp.text[:200]}")
            return None, None

        audio_chunks = []
        word_timestamps = []

        # Parse SSE stream
        event_type = None
        data_buffer = ""

        for line in resp.iter_lines(decode_unicode=True):
            if line is None:
                continue

            if line.startswith("event:"):
                event_type = line[6:].strip()
                data_buffer = ""
            elif line.startswith("data:"):
                data_buffer = line[5:].strip()

                if event_type == "chunk" and data_buffer:
                    try:
                        chunk_data = json.loads(data_buffer)
                        audio_b64 = chunk_data.get("data", "")
                        if audio_b64:
                            audio_chunks.append(base64.b64decode(audio_b64))
                    except (json.JSONDecodeError, KeyError):
                        pass

                elif event_type == "timestamps" and data_buffer:
                    try:
                        ts_data = json.loads(data_buffer)
                        words = ts_data.get("words", [])
                        starts = ts_data.get("start", [])
                        ends = ts_data.get("end", [])
                        for w, s, e in zip(words, starts, ends):
                            word_timestamps.append({
                                "word": w,
                                "start_s": float(s),
                                "end_s": float(e),
                            })
                    except (json.JSONDecodeError, KeyError):
                        pass

            elif line == "":
                event_type = None
                data_buffer = ""

        if not audio_chunks:
            print("  No audio chunks received from SSE")
            return None, None

        # Write raw PCM to WAV
        raw_audio = b"".join(audio_chunks)
        _write_pcm_to_wav(raw_audio, CARTESIA_SAMPLE_RATE, output_path)

        duration = len(raw_audio) / (CARTESIA_SAMPLE_RATE * 4)  # 4 bytes per float32

        # If no timestamps came through, estimate them
        if not word_timestamps:
            word_timestamps = _estimate_word_timestamps(text, duration)

        return duration, word_timestamps

    except Exception as e:
        print(f"  Cartesia SSE exception: {e}")
        return None, None


def _write_pcm_to_wav(raw_pcm, sample_rate, output_path):
    """Write raw PCM float32 LE bytes to a proper WAV file."""
    num_channels = 1
    bits_per_sample = 32
    byte_rate = sample_rate * num_channels * bits_per_sample // 8
    block_align = num_channels * bits_per_sample // 8
    data_size = len(raw_pcm)

    with open(output_path, "wb") as f:
        # RIFF header
        f.write(b"RIFF")
        f.write(struct.pack("<I", 36 + data_size))
        f.write(b"WAVE")
        # fmt chunk (format 3 = IEEE float)
        f.write(b"fmt ")
        f.write(struct.pack("<I", 16))
        f.write(struct.pack("<H", 3))  # IEEE float
        f.write(struct.pack("<H", num_channels))
        f.write(struct.pack("<I", sample_rate))
        f.write(struct.pack("<I", byte_rate))
        f.write(struct.pack("<H", block_align))
        f.write(struct.pack("<H", bits_per_sample))
        # data chunk
        f.write(b"data")
        f.write(struct.pack("<I", data_size))
        f.write(raw_pcm)


def _cartesia_bytes(text, output_path):
    """Fallback: Cartesia bytes endpoint (no timestamps)."""
    headers = {
        "X-API-Key": CARTESIA_API_KEY,
        "Cartesia-Version": "2025-04-16",
        "Content-Type": "application/json",
    }
    payload = {
        "model_id": CARTESIA_MODEL,
        "transcript": text,
        "voice": {"mode": "id", "id": SHORTS_VOICE_ID},
        "output_format": {
            "container": "wav",
            "encoding": "pcm_f32le",
            "sample_rate": CARTESIA_SAMPLE_RATE,
        },
        "language": "en",
    }

    resp = requests.post(
        "https://api.cartesia.ai/tts/bytes",
        json=payload, headers=headers, timeout=60,
    )

    if resp.status_code == 200 and len(resp.content) > 1000:
        with open(output_path, "wb") as f:
            f.write(resp.content)
        return _get_wav_duration(output_path)

    print(f"  Cartesia bytes error: {resp.status_code} - {resp.text[:200]}")
    return None


def _get_wav_duration(path):
    """Get duration of a WAV file in seconds."""
    try:
        file_size = os.path.getsize(path)
        with open(path, "rb") as f:
            f.read(4)  # RIFF
            f.read(4)  # size
            f.read(4)  # WAVE
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
    except Exception:
        pass
    size = os.path.getsize(path)
    return size / (CARTESIA_SAMPLE_RATE * 4)


def _estimate_word_timestamps(text, total_duration_s):
    """Estimate word-level timestamps proportional to character count."""
    words = text.split()
    if not words:
        return []

    total_chars = sum(len(w) for w in words)
    if total_chars == 0:
        return []

    timestamps = []
    current_s = 0.0
    for word in words:
        word_duration = (len(word) / total_chars) * total_duration_s
        timestamps.append({
            "word": word,
            "start_s": round(current_s, 3),
            "end_s": round(current_s + word_duration, 3),
        })
        current_s += word_duration

    return timestamps


def _kokoro_fallback(text, output_path):
    """Fallback: Kokoro local TTS with estimated timestamps."""
    try:
        from kokoro_onnx import Kokoro
        import soundfile as sf

        kokoro = Kokoro(KOKORO_MODEL_PATH, KOKORO_VOICES_PATH)

        clean = text.replace("...", ", ").strip()
        clean = re.sub(r'\s+', ' ', clean)

        samples, sr = kokoro.create(clean, voice=KOKORO_VOICE, speed=KOKORO_SPEED)
        sf.write(output_path, samples, sr)

        duration = len(samples) / sr
        timestamps = _estimate_word_timestamps(clean, duration)
        return duration, timestamps
    except Exception as e:
        print(f"  Kokoro fallback failed: {e}")
        return None, None


if __name__ == "__main__":
    test_text = (
        "Why are African mechanics so muscular? "
        "They have no gym, no machines, and most are poor. "
        "But their solution is lifting heavy engine parts every single day."
    )
    duration, timestamps = generate_narration_with_timestamps(
        test_text, os.path.join(OUTPUT_DIR, "audio", "test_narration.wav")
    )
    if timestamps:
        print(f"\nFirst 10 word timestamps:")
        for ts in timestamps[:10]:
            print(f"  {ts['start_s']:.3f} - {ts['end_s']:.3f}: {ts['word']}")
