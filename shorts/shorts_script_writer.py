"""
Shorts script schema, validation, and prompt generation.
"""

import os
import json
import re

from shorts_config import OUTPUT_DIR


# Banned phrases (subset from main pipeline CLAUDE.md)
BANNED_PHRASES = [
    "delve", "delving", "dive into", "deep dive", "unpack",
    "game-changer", "game-changing", "revolutionize", "revolutionary",
    "realm", "tapestry", "testament", "nuance", "nuanced",
    "paradigm", "paradigm shift", "leverage", "utilize", "facilitate",
    "foster", "synergy", "holistic", "robust", "seamless", "seamlessly",
    "cutting-edge", "groundbreaking", "transformative", "pivotal",
    "multifaceted", "comprehensive", "navigate",
    "it's important to note", "it's worth mentioning",
    "at the end of the day", "moving forward",
    "passive income", "get rich quick", "easy money",
]

# AI tool names for niche validation
AI_TOOL_NAMES = [
    "chatgpt", "gpt", "claude", "midjourney", "runway", "dall-e", "dalle",
    "stable diffusion", "copilot", "cursor", "replit", "v0", "bolt",
    "elevenlabs", "synthesia", "heygen", "opus clip", "descript",
    "jasper", "writesonic", "copy.ai", "perplexity", "gemini",
    "anthropic", "openai", "meta ai", "llama", "mistral",
]


def load_shorts_script(path=None):
    """Load and normalize a Shorts script JSON.

    Returns the script dict or None on error.
    """
    if path is None:
        path = os.path.join(OUTPUT_DIR, "script.json")

    if not os.path.exists(path):
        print(f"  Script not found: {path}")
        return None

    with open(path, "r", encoding="utf-8") as f:
        script = json.load(f)

    # Normalize
    if "segments" not in script:
        script["segments"] = []

    for i, seg in enumerate(script["segments"]):
        seg.setdefault("segment_id", i + 1)
        seg.setdefault("annotations", [])
        seg.setdefault("duration_hint_s", 5.0)

    script.setdefault("tags", [])
    script.setdefault("source_video", {})

    return script


def validate_shorts_script(script):
    """Validate a Shorts script against rules.

    Returns: (is_valid, list_of_issues)
    """
    issues = []

    # Required fields
    if not script.get("title"):
        issues.append("Missing 'title'")
    if not script.get("full_narration"):
        issues.append("Missing 'full_narration'")

    narration = script.get("full_narration", "")
    segments = script.get("segments", [])
    source = script.get("source_video", {})

    # Source video
    if not source.get("url") and not source.get("search_query"):
        issues.append("source_video needs either 'url' or 'search_query'")

    # Segment count
    if len(segments) < 2:
        issues.append(f"Too few segments ({len(segments)}), need at least 2")
    if len(segments) > 12:
        issues.append(f"Too many segments ({len(segments)}), max 12 for a Short")

    # Narration length (word count)
    word_count = len(narration.split())
    if word_count < 15:
        issues.append(f"Narration too short ({word_count} words), need at least 15")
    if word_count > 120:
        issues.append(f"Narration too long ({word_count} words), max 120 for ~30-60s")

    # Segment time ranges
    for seg in segments:
        start = seg.get("video_start_s", 0)
        end = seg.get("video_end_s", start + 5)
        if end <= start:
            issues.append(f"Segment {seg['segment_id']}: video_end_s must be > video_start_s")

    # Banned phrases
    lower_narration = narration.lower()
    for phrase in BANNED_PHRASES:
        if phrase.lower() in lower_narration:
            issues.append(f"Banned phrase found: '{phrase}'")

    # Sentence length (max 25 words per sentence)
    sentences = re.split(r'[.!?]+', narration)
    for sent in sentences:
        words = sent.strip().split()
        if len(words) > 25:
            issues.append(f"Sentence too long ({len(words)} words): '{sent.strip()[:50]}...'")

    # Niche-specific validation (ai_money)
    if script.get("niche") == "ai_money":
        lower = narration.lower()
        # Must mention at least one AI tool
        has_tool = any(tool in lower for tool in AI_TOOL_NAMES)
        if not has_tool:
            issues.append("AI money niche: narration must mention at least one AI tool name")
        # Must contain a dollar amount or number
        has_amount = bool(re.search(r'\b(thousand|million|hundred|\d+[kK]|\$\d)', narration, re.IGNORECASE))
        if not has_amount:
            issues.append("AI money niche: narration must contain a dollar amount or revenue figure")

    is_valid = len(issues) == 0

    if is_valid:
        print(f"  Script validation PASSED ({word_count} words, {len(segments)} segments)")
    else:
        print(f"  Script validation FAILED ({len(issues)} issues):")
        for issue in issues:
            print(f"    - {issue}")

    return is_valid, issues


def generate_shorts_prompt(topic, source_url=None):
    """Generate the prompt for a Claude subagent to create a Shorts script.

    Args:
        topic: The topic/theme for the Short (e.g., "African mechanics muscles")
        source_url: Optional YouTube URL of the source video

    Returns: prompt string
    """
    return f"""Generate a YouTube Shorts script JSON for a ~30-second motivational/documentary short.

TOPIC: {topic}
{f'SOURCE VIDEO: {source_url}' if source_url else ''}

OUTPUT FORMAT (strict JSON):
{{
    "title": "Catchy title for the Short (max 60 chars)",
    "description": "YouTube description (2-3 sentences)",
    "tags": ["relevant", "tags", "here"],
    "full_narration": "The complete voiceover narration as one flowing text. 30-80 words. Punchy, dramatic, conversational. Use contractions. Short sentences for impact.",
    "source_video": {{
        {"\"url\": \"" + source_url + "\"" if source_url else "\"search_query\": \"specific 5+ word YouTube search query to find the source video\""}
    }},
    "segments": [
        {{
            "segment_id": 1,
            "narration": "The portion of full_narration for this segment",
            "video_start_s": 0.0,
            "video_end_s": 5.0,
            "duration_hint_s": 5.0,
            "annotations": [
                {{"type": "circle", "x": 0.5, "y": 0.4, "radius": 0.12, "start_s": 0.5, "end_s": 2.0}}
            ]
        }}
    ]
}}

RULES:
- full_narration: 30-80 words. Written as ONE flowing piece. Dramatic, punchy.
- 4-8 segments total. Each segment = a different moment from the source video.
- video_start_s / video_end_s = time range in the SOURCE VIDEO to extract.
- duration_hint_s = how long this segment appears in the final Short.
- Annotations are optional — use a red circle to highlight subjects in 1-2 segments max.
- BANNED: "delve", "dive into", "game-changer", "revolutionary", "leverage", "utilize", "seamless", "groundbreaking", "transformative", "paradigm"
- Use contractions: "they're" not "they are", "it's" not "it is"
- No sentence longer than 25 words
- Start with a hook question or bold statement
- End with a punchy conclusion, NOT "like and subscribe"
"""


def generate_ai_money_shorts_prompt(topic, source_url=None, clip_manifest=None):
    """Generate prompt for Claude to write an AI money-making Shorts script.

    Args:
        topic: Description of the video content
        source_url: YouTube URL of the source video
        clip_manifest: Dict with segment timings from clip_manifest.json

    Returns: prompt string
    """
    segments_info = ""
    if clip_manifest and clip_manifest.get("segments"):
        segs = clip_manifest["segments"]
        segments_info = f"\nYou have {len(segs)} prepared video clips:\n"
        for s in segs:
            segments_info += f"  - Segment {s['segment_id']}: {s['video_start_s']}s-{s['video_end_s']}s ({s['duration_hint_s']}s) — {s.get('description', '')}\n"
        segments_info += f"\nTotal clip duration: {clip_manifest.get('total_short_duration_s', 45)}s\n"
        segments_info += "Map your narration segments to these clip timings.\n"

    return f"""Generate a YouTube Shorts script JSON for a ~30-60 second Short about making money with AI tools.

TOPIC: {topic}
{f'SOURCE VIDEO: {source_url}' if source_url else ''}
{segments_info}

NICHE: ai_money — This Short is about people making real money using AI automation, agentic tools, faceless content, or vibe coding.

OUTPUT FORMAT (strict JSON):
{{
    "title": "Catchy title (max 60 chars, include dollar amount)",
    "description": "YouTube description (2-3 sentences)",
    "tags": ["shorts", "ai", "money", "automation"],
    "niche": "ai_money",
    "full_narration": "Complete voiceover as ONE flowing text. 30-80 words. Spell out numbers for TTS (forty seven thousand, not $47K).",
    "source_video": {{
        {'"url": "' + source_url + '"' if source_url else '"search_query": "specific YouTube search query"'}
    }},
    "segments": [
        {{
            "segment_id": 1,
            "narration": "Exact substring of full_narration for this segment",
            "video_start_s": 0.0,
            "video_end_s": 5.0,
            "duration_hint_s": 5.0,
            "annotations": []
        }}
    ],
    "thumbnail": {{
        "layout": "hero_right",
        "headline": "*$47K* in *2 DAYS*",
        "image_search_query": "specific visual from the video"
    }}
}}

HOOK PATTERNS (use one of these):
- "How this guy made [amount] in [time] using [AI tool]"
- "Three AI tools that are making people rich right now"
- "Nobody's talking about this AI money hack"
- "This AI tool is printing money and nobody knows about it"

REQUIREMENTS:
- At least 1 specific AI tool name (ChatGPT, Claude, Midjourney, etc.)
- At least 1 specific dollar amount spelled out (forty seven thousand, not $47K)
- At least 1 "proof" moment referencing visual evidence
- 4-8 segments matching available clips
- No sentence longer than 25 words
- Use contractions: "it's", "they're", "won't"
- full_narration is ONE flowing piece, not fragments joined

BANNED: "delve", "dive into", "game-changer", "revolutionary", "leverage", "utilize", "seamless", "groundbreaking", "passive income", "get rich quick", "easy money", "like and subscribe", "thanks for watching"

THUMBNAIL: headline 3-6 words with *asterisks* for red accent, layout hero_right/hero_left/center_dramatic
"""


if __name__ == "__main__":
    # Test: load and validate sample script
    sample_path = os.path.join(OUTPUT_DIR, "script.json")
    if os.path.exists(sample_path):
        script = load_shorts_script(sample_path)
        if script:
            validate_shorts_script(script)
    else:
        print(f"  No script at {sample_path} — create one first")
