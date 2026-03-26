"""
Cartesia Sonic TTS engine — generates per-scene audio with estimated word timestamps.
Falls back to Kokoro TTS if Cartesia API fails.
"""

import os
import re
import io
import struct
import requests
import numpy as np
from config import CARTESIA_API_KEY, CARTESIA_VOICE_ID

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CARTESIA_MODEL = "sonic"
CARTESIA_SAMPLE_RATE = 44100

# Kokoro fallback settings
MODEL_PATH = os.path.join(BASE_DIR, "assets", "models", "kokoro-v1.0.onnx")
VOICES_PATH = os.path.join(BASE_DIR, "assets", "models", "voices-v1.0.bin")
KOKORO_VOICE = "am_adam"
KOKORO_SPEED = 1.15


def _cartesia_tts(text, output_path):
    """Generate audio via Cartesia Sonic API. Returns True on success."""
    headers = {
        "X-API-Key": CARTESIA_API_KEY,
        "Cartesia-Version": "2025-04-16",
        "Content-Type": "application/json",
    }
    payload = {
        "model_id": CARTESIA_MODEL,
        "transcript": text,
        "voice": {"mode": "id", "id": CARTESIA_VOICE_ID},
        "output_format": {
            "container": "wav",
            "encoding": "pcm_f32le",
            "sample_rate": CARTESIA_SAMPLE_RATE,
        },
        "language": "en",
    }

    resp = requests.post(
        "https://api.cartesia.ai/tts/bytes",
        json=payload,
        headers=headers,
        timeout=60,
    )

    if resp.status_code == 200 and len(resp.content) > 1000:
        with open(output_path, "wb") as f:
            f.write(resp.content)
        return True

    print(f"  Cartesia API error: {resp.status_code} - {resp.text[:200]}")
    return False


def _get_wav_duration(path):
    """Get duration of a WAV file in seconds."""
    try:
        file_size = os.path.getsize(path)
        with open(path, "rb") as f:
            f.read(4)  # RIFF
            f.read(4)  # size
            f.read(4)  # WAVE
            # Find fmt and data chunks
            data_offset = None
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
                    data_offset = f.tell()
                    bytes_per_sample = bits_per_sample // 8
                    # Handle streaming WAVs where data size is 0xFFFFFFFF
                    if chunk_size >= 0xFFFFFFFF - 1:
                        actual_data_size = file_size - data_offset
                    else:
                        actual_data_size = chunk_size
                    num_samples = actual_data_size // (bytes_per_sample * channels)
                    return num_samples / sample_rate
                else:
                    f.seek(chunk_size, 1)
    except Exception:
        pass
    # Fallback: estimate from file size (assume 32-bit float mono)
    size = os.path.getsize(path)
    return size / (CARTESIA_SAMPLE_RATE * 4)



def _estimate_word_timestamps(text, total_duration_s):
    """Estimate word-level timestamps based on word count and audio duration."""
    words = text.split()
    if not words:
        return []

    total_chars = sum(len(w) for w in words)
    if total_chars == 0:
        return []

    subs = []
    current_ms = 0.0
    for word in words:
        word_duration_ms = (len(word) / total_chars) * total_duration_s * 1000
        subs.append({
            "text": word,
            "start_ms": round(current_ms),
            "end_ms": round(current_ms + word_duration_ms),
        })
        current_ms += word_duration_ms

    return subs


def _generate_scene_cartesia(text, output_path):
    """Generate audio for one scene via Cartesia. Handles '...' pauses."""
    segments = re.split(r'\.{3,}', text)
    segments = [s.strip() for s in segments if s.strip()]

    if len(segments) <= 1:
        clean = text.replace("...", " ").strip()
        clean = re.sub(r'\s+', ' ', clean)
        success = _cartesia_tts(clean, output_path)
        if not success:
            return None, None
        duration = _get_wav_duration(output_path)
        subs = _estimate_word_timestamps(clean, duration)
        return duration, subs

    # Multiple segments: generate each, concatenate with silence
    import soundfile as sf
    all_samples = []
    sample_rate = CARTESIA_SAMPLE_RATE

    for i, segment in enumerate(segments):
        seg_path = output_path + f".seg{i}.wav"
        success = _cartesia_tts(segment, seg_path)
        if not success:
            return None, None

        data, sr = sf.read(seg_path)
        sample_rate = sr
        all_samples.append(data)

        # 300ms silence between segments
        if i < len(segments) - 1:
            silence = np.zeros(int(sr * 0.3), dtype=data.dtype)
            all_samples.append(silence)

        os.remove(seg_path)

    combined = np.concatenate(all_samples)
    sf.write(output_path, combined, sample_rate)

    duration = len(combined) / sample_rate
    clean = text.replace("...", " ").strip()
    clean = re.sub(r'\s+', ' ', clean)
    subs = _estimate_word_timestamps(clean, duration)
    return duration, subs


def _generate_scene_kokoro_fallback(text, output_path):
    """Fallback: generate audio using Kokoro TTS."""
    try:
        from kokoro_onnx import Kokoro
        import soundfile as sf

        kokoro = Kokoro(MODEL_PATH, VOICES_PATH)
        segments = re.split(r'\.{3,}', text)
        segments = [s.strip() for s in segments if s.strip()]

        all_samples = []
        sample_rate = None

        for i, segment in enumerate(segments):
            samples, sr = kokoro.create(segment, voice=KOKORO_VOICE, speed=KOKORO_SPEED)
            sample_rate = sr
            all_samples.append(samples)
            if i < len(segments) - 1:
                all_samples.append(np.zeros(int(sr * 0.3), dtype=samples.dtype))

        combined = np.concatenate(all_samples)
        sf.write(output_path, combined, sample_rate)

        duration = len(combined) / sample_rate
        clean = text.replace("...", " ").strip()
        clean = re.sub(r'\s+', ' ', clean)
        subs = _estimate_word_timestamps(clean, duration)
        return duration, subs
    except Exception as e:
        print(f"  Kokoro fallback failed: {e}")
        return None, None


def generate_scene_audio(scenes, output_dir="output/audio"):
    """Generate audio for each scene. Returns list of {audio_path, duration_seconds, subtitles}."""
    os.makedirs(output_dir, exist_ok=True)

    results = []
    use_cartesia = True

    for i, scene in enumerate(scenes):
        narration = scene.get("narration", "")
        if not narration:
            continue

        scene_num = str(i + 1).zfill(3)
        audio_path = os.path.join(output_dir, f"scene_{scene_num}.wav")

        duration, subs = None, None

        if use_cartesia:
            duration, subs = _generate_scene_cartesia(narration, audio_path)
            if duration is None:
                print(f"  Scene {i+1}: Cartesia failed, falling back to Kokoro...")
                use_cartesia = False

        if duration is None:
            duration, subs = _generate_scene_kokoro_fallback(narration, audio_path)

        if duration is None:
            print(f"  ERROR: All TTS engines failed for scene {i+1}")
            continue

        results.append({
            "scene_index": i,
            "audio_path": audio_path,
            "duration_seconds": round(duration, 2),
            "subtitles": subs or [],
        })

    total = sum(r["duration_seconds"] for r in results)
    engine = "Cartesia Sonic" if use_cartesia else "Kokoro (fallback)"
    print(f"  Generated {len(results)} scene audio files ({total:.1f}s total) via {engine}.")
    return results


def generate_continuous_audio(full_narration, output_path="output/audio/full_narration.wav"):
    """Generate ONE continuous audio file from the full narration text.

    Sends the entire narration to Cartesia in one call for fluid, natural speech.
    If text exceeds API limits, splits at paragraph/sentence boundaries (few chunks).
    Falls back to Kokoro if Cartesia fails.

    Returns: total_duration_seconds or None on failure.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Clean pause markers for TTS — replace ... with commas for natural pauses
    clean_text = full_narration.replace("...", ", ").strip()
    clean_text = re.sub(r'\s+', ' ', clean_text)

    if not clean_text:
        print("  ERROR: Empty narration text.")
        return None

    # Try full text in one Cartesia call first
    print(f"  Generating continuous audio ({len(clean_text)} chars)...")
    success = _cartesia_tts(clean_text, output_path)

    if success:
        duration = _get_wav_duration(output_path)
        print(f"  Continuous audio generated: {duration:.1f}s via Cartesia Sonic (single call)")
        return duration

    # If single call failed, try chunking at sentence boundaries
    print("  Single call failed, trying paragraph chunking...")
    duration = _generate_chunked_audio(clean_text, output_path)
    if duration:
        return duration

    # Kokoro fallback
    print("  Cartesia chunking failed, trying Kokoro fallback...")
    duration = _generate_continuous_kokoro(full_narration, output_path)
    return duration


def _generate_chunked_audio(text, output_path, max_chunk_chars=2000):
    """Split text at sentence boundaries and generate audio chunks, then concatenate."""
    import soundfile as sf

    # Split into sentences
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks = []
    current_chunk = ""

    for sentence in sentences:
        if len(current_chunk) + len(sentence) > max_chunk_chars and current_chunk:
            chunks.append(current_chunk.strip())
            current_chunk = sentence
        else:
            current_chunk = f"{current_chunk} {sentence}".strip()
    if current_chunk:
        chunks.append(current_chunk.strip())

    print(f"  Split into {len(chunks)} chunks for TTS...")

    all_samples = []
    sample_rate = CARTESIA_SAMPLE_RATE

    for i, chunk in enumerate(chunks):
        chunk_path = output_path + f".chunk{i}.wav"
        success = _cartesia_tts(chunk, chunk_path)
        if not success:
            # Clean up
            for j in range(i):
                p = output_path + f".chunk{j}.wav"
                if os.path.exists(p):
                    os.remove(p)
            return None

        data, sr = sf.read(chunk_path)
        sample_rate = sr
        all_samples.append(data)

        # Tiny silence between chunks (100ms — barely noticeable)
        if i < len(chunks) - 1:
            silence = np.zeros(int(sr * 0.1), dtype=data.dtype)
            all_samples.append(silence)

        os.remove(chunk_path)

    combined = np.concatenate(all_samples)
    sf.write(output_path, combined, sample_rate)

    duration = len(combined) / sample_rate
    print(f"  Chunked audio generated: {duration:.1f}s via Cartesia Sonic ({len(chunks)} chunks)")
    return duration


def _generate_continuous_kokoro(full_narration, output_path):
    """Fallback: generate continuous audio using Kokoro TTS."""
    try:
        from kokoro_onnx import Kokoro
        import soundfile as sf

        kokoro = Kokoro(MODEL_PATH, VOICES_PATH)

        clean = full_narration.replace("...", ", ").strip()
        clean = re.sub(r'\s+', ' ', clean)

        # Kokoro handles long text well locally — split at ~1000 chars
        sentences = re.split(r'(?<=[.!?])\s+', clean)
        chunks = []
        current = ""
        for sent in sentences:
            if len(current) + len(sent) > 1000 and current:
                chunks.append(current.strip())
                current = sent
            else:
                current = f"{current} {sent}".strip()
        if current:
            chunks.append(current.strip())

        all_samples = []
        sample_rate = None

        for i, chunk in enumerate(chunks):
            samples, sr = kokoro.create(chunk, voice=KOKORO_VOICE, speed=KOKORO_SPEED)
            sample_rate = sr
            all_samples.append(samples)
            if i < len(chunks) - 1:
                all_samples.append(np.zeros(int(sr * 0.1), dtype=samples.dtype))

        combined = np.concatenate(all_samples)
        sf.write(output_path, combined, sample_rate)

        duration = len(combined) / sample_rate
        print(f"  Continuous audio generated: {duration:.1f}s via Kokoro (fallback)")
        return duration
    except Exception as e:
        print(f"  Kokoro continuous fallback failed: {e}")
        return None


def calculate_scene_durations(scenes, total_duration):
    """Calculate each scene's duration proportional to its narration length.

    Returns list of floats (duration in seconds for each scene).
    """
    char_counts = [len(s.get("narration", "").replace("...", "")) for s in scenes]
    total_chars = sum(char_counts)
    if total_chars == 0:
        return [total_duration / len(scenes)] * len(scenes)

    durations = [(c / total_chars) * total_duration for c in char_counts]
    return durations


if __name__ == "__main__":
    sample_text = (
        "OpenAI just killed Sora. The Wall Street Journal broke this Tuesday, "
        "and nobody saw it coming. This wasn't a pivot or a rebrand. "
        "They straight up pulled the plug on their most hyped product."
    )
    duration = generate_continuous_audio(sample_text, "output/audio/test_continuous.wav")
    if duration:
        print(f"  Test audio: {duration:.1f}s")
