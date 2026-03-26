"""QA review functions for generated videos — called by Claude Code agents before assembly."""

import os
import json
from datetime import datetime

from database import get_connection


def review_video_quality(script_data, frame_paths, audio_duration):
    """Comprehensive QA review of a generated video.

    Args:
        script_data: dict with title, scenes, full_narration
        frame_paths: list of PNG paths
        audio_duration: float seconds

    Returns dict:
        virality_prediction: 0-100 score
        issues: list of issue strings
        strengths: list of strength strings
        recommendations: list of action strings
        overall_grade: A/B/C/D/F
    """
    issues = []
    strengths = []
    recommendations = []
    virality = 50  # base score

    title = script_data.get("title", "")
    scenes = script_data.get("scenes", [])
    narration = script_data.get("full_narration", "")

    # Title analysis
    title_len = len(title)
    if title_len > 60:
        issues.append(f"Title too long ({title_len} chars) — may get truncated in search")
    elif title_len < 30:
        issues.append(f"Title too short ({title_len} chars) — may lack keywords")

    if any(c.isdigit() for c in title):
        strengths.append("Title contains numbers — higher CTR")
        virality += 5

    # Check for power words in title
    power_words = [
        "just", "breaking", "killed", "leaked", "secret", "finally",
        "biggest", "worst", "best", "new", "why", "how",
    ]
    title_lower = title.lower()
    power_count = sum(1 for w in power_words if w in title_lower)
    if power_count >= 2:
        strengths.append(f"Title has {power_count} power words — strong clickability")
        virality += 10
    elif power_count == 0:
        issues.append("Title lacks power words — may underperform on CTR")
        virality -= 5

    # Scene count analysis
    if len(scenes) < 10:
        issues.append(f"Only {len(scenes)} scenes — may feel like a slideshow")
        virality -= 10
    elif len(scenes) >= 15:
        strengths.append(f"{len(scenes)} scenes — good visual variety")
        virality += 5

    # Duration analysis
    if audio_duration < 180:
        issues.append(f"Video only {audio_duration:.0f}s — under 3min may hurt retention")
        virality -= 5
    elif 240 <= audio_duration <= 360:
        strengths.append(f"Video {audio_duration:.0f}s — sweet spot for watch time")
        virality += 10

    # Visual variety check
    visual_types = [s.get("visual_type", "") for s in scenes]
    unique_types = len(set(visual_types))
    if unique_types < 3:
        issues.append(f"Only {unique_types} visual types used — needs more variety")
        virality -= 5
    elif unique_types >= 5:
        strengths.append(f"{unique_types} different visual types — great variety")
        virality += 5

    # Check for consecutive same types
    consecutive_same = 0
    for i in range(1, len(visual_types)):
        if visual_types[i] == visual_types[i - 1]:
            consecutive_same += 1
    if consecutive_same > 0:
        issues.append(f"{consecutive_same} consecutive same-type scenes — breaks visual rhythm")

    # Meme check
    meme_count = sum(1 for v in visual_types if v == "meme_fullscreen")
    if meme_count == 0:
        recommendations.append("Add 2-3 meme moments for humor beats")
    elif 2 <= meme_count <= 4:
        strengths.append(f"{meme_count} meme moments — good humor density")
        virality += 5

    # Narration quality
    word_count = len(narration.split())
    if word_count < 500:
        issues.append(f"Only {word_count} words — thin content")
    elif word_count >= 800:
        strengths.append(f"{word_count} words — substantial content depth")
        virality += 5

    # Frame file check
    missing_frames = [p for p in frame_paths if not os.path.exists(p)]
    if missing_frames:
        issues.append(f"{len(missing_frames)} frames missing from disk")

    # Clamp virality
    virality = max(0, min(100, virality))

    # Grade
    if virality >= 80:
        grade = "A"
    elif virality >= 65:
        grade = "B"
    elif virality >= 50:
        grade = "C"
    elif virality >= 35:
        grade = "D"
    else:
        grade = "F"

    # Generate recommendations
    if virality < 60:
        recommendations.append("Consider a stronger hook in the first sentence")
    if "?" not in title:
        recommendations.append("Questions in titles can boost CTR")

    return {
        "virality_prediction": virality,
        "issues": issues,
        "strengths": strengths,
        "recommendations": recommendations,
        "overall_grade": grade,
        "reviewed_at": datetime.now().isoformat(),
    }


def review_title_description(title, description):
    """Review title and description for YouTube optimization.
    Returns dict with score, issues, recommendations."""
    issues = []
    recommendations = []
    score = 50

    # Title checks
    if len(title) > 60:
        issues.append("Title > 60 chars — will be truncated")
    if title == title.upper():
        issues.append("ALL CAPS title — YouTube may suppress")
    if not any(c.isdigit() for c in title):
        recommendations.append("Add a number to the title for higher CTR")

    # Description checks
    if len(description) < 100:
        issues.append("Description too short — hurts SEO")
        recommendations.append("Add 2-3 paragraph description with keywords")

    desc_lower = description.lower()
    if "timestamp" not in desc_lower and "00:" not in description:
        recommendations.append("Add timestamps/chapters to description")

    return {"score": score, "issues": issues, "recommendations": recommendations}


def generate_qa_report(video_review, title_review=None):
    """Combine all QA results into a formatted report string."""
    lines = []
    lines.append(
        f"## QA Report — Grade: {video_review['overall_grade']} "
        f"(Virality: {video_review['virality_prediction']}/100)"
    )
    lines.append("")

    if video_review["strengths"]:
        lines.append("### Strengths")
        for s in video_review["strengths"]:
            lines.append(f"  + {s}")
        lines.append("")

    if video_review["issues"]:
        lines.append("### Issues")
        for i in video_review["issues"]:
            lines.append(f"  - {i}")
        lines.append("")

    if video_review["recommendations"]:
        lines.append("### Recommendations")
        for r in video_review["recommendations"]:
            lines.append(f"  > {r}")

    return "\n".join(lines)
