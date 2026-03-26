"""QA review functions for generated videos — called by Claude Code agents before assembly."""

import os
import json
from datetime import datetime

from database import get_connection


def review_video_quality(script_data, frame_paths, audio_duration):
    """Comprehensive QA review of a generated video against the 5 virality pillars.

    Args:
        script_data: dict with title, scenes, full_narration
        frame_paths: list of PNG paths
        audio_duration: float seconds

    Returns dict:
        virality_prediction: 0-100 score
        pillar_scores: dict of pillar name -> 0-100
        issues: list of issue strings
        strengths: list of strength strings
        recommendations: list of action strings
        overall_grade: A/B/C/D/F
    """
    issues = []
    strengths = []
    recommendations = []

    title = script_data.get("title", "")
    scenes = script_data.get("scenes", [])
    narration = script_data.get("full_narration", "")
    visual_types = [s.get("visual_type", "") for s in scenes]

    # -----------------------------------------------------------------------
    # Pillar 1: THE HOOK (First 5s) — Does the opening grab attention?
    # -----------------------------------------------------------------------
    hook_pillar = 50  # base

    # Check first scene narration for a strong hook
    first_narration = scenes[0].get("narration", "") if scenes else ""
    first_words = first_narration.split()

    # Starts with a surprising fact, question, or bold claim?
    if first_narration and ("?" in first_narration[:80]):
        strengths.append("Pillar 1 (Hook): Opens with a question — grabs attention")
        hook_pillar += 15
    elif first_words and first_words[0].lower() in ("why", "what", "how", "if"):
        strengths.append("Pillar 1 (Hook): Opens with curiosity trigger")
        hook_pillar += 10

    # Check for numbers/specifics in first sentence
    if any(c.isdigit() for c in first_narration[:60]):
        strengths.append("Pillar 1 (Hook): First sentence has specific numbers")
        hook_pillar += 10

    # Check first visual type — arresting visuals score higher
    if visual_types:
        arresting_types = {"text_bold", "fullscreen_image", "meme_fullscreen"}
        if visual_types[0] in arresting_types:
            strengths.append(f"Pillar 1 (Hook): Strong opening visual ({visual_types[0]})")
            hook_pillar += 10
        else:
            issues.append(f"Pillar 1 (Hook): Opening visual is {visual_types[0]} — consider text_bold or fullscreen_image")
            hook_pillar -= 5

    # Penalize generic openings
    generic_openers = ["hey everyone", "welcome back", "in today's video", "so,", "let's dive"]
    if any(first_narration.lower().startswith(g) for g in generic_openers):
        issues.append("Pillar 1 (Hook): Generic opening detected — violates hook rules")
        hook_pillar -= 20

    # Word count of first sentence — short = punchy
    first_sentence_end = min(
        first_narration.find(".") if "." in first_narration else 999,
        first_narration.find("?") if "?" in first_narration else 999,
        first_narration.find("!") if "!" in first_narration else 999,
    )
    if 0 < first_sentence_end <= 50:
        hook_pillar += 5  # punchy

    hook_pillar = max(0, min(100, hook_pillar))

    # -----------------------------------------------------------------------
    # Pillar 2: THE CLICK (Title+Thumbnail) — Does packaging compel clicks?
    # -----------------------------------------------------------------------
    click_pillar = 50  # base

    title_len = len(title)
    if 40 <= title_len <= 60:
        strengths.append(f"Pillar 2 (Click): Title length optimal ({title_len} chars)")
        click_pillar += 15
    elif title_len > 60:
        issues.append(f"Pillar 2 (Click): Title too long ({title_len} chars) — will be truncated")
        click_pillar -= 10
    elif title_len < 30:
        issues.append(f"Pillar 2 (Click): Title too short ({title_len} chars)")
        click_pillar -= 5

    if any(c.isdigit() for c in title):
        strengths.append("Pillar 2 (Click): Title has numbers — higher CTR")
        click_pillar += 10

    power_words = [
        "just", "breaking", "killed", "leaked", "secret", "finally",
        "biggest", "worst", "best", "new", "why", "how", "dead", "free",
    ]
    title_lower = title.lower()
    power_count = sum(1 for w in power_words if w in title_lower)
    if power_count >= 2:
        strengths.append(f"Pillar 2 (Click): {power_count} power words in title")
        click_pillar += 15
    elif power_count == 0:
        issues.append("Pillar 2 (Click): No power words in title")
        click_pillar -= 10

    if "?" in title:
        strengths.append("Pillar 2 (Click): Question in title — curiosity gap")
        click_pillar += 10

    if title == title.upper():
        issues.append("Pillar 2 (Click): ALL CAPS title — YouTube may suppress")
        click_pillar -= 10

    click_pillar = max(0, min(100, click_pillar))

    # -----------------------------------------------------------------------
    # Pillar 3: THE RETENTION (Keep Watching) — Do viewers stay?
    # -----------------------------------------------------------------------
    retention_pillar = 50  # base

    # Visual type variety
    unique_types = len(set(visual_types))
    if unique_types >= 5:
        strengths.append(f"Pillar 3 (Retention): {unique_types} visual types — great variety")
        retention_pillar += 15
    elif unique_types < 3:
        issues.append(f"Pillar 3 (Retention): Only {unique_types} visual types — monotonous")
        retention_pillar -= 10

    # Consecutive same types
    consecutive_same = 0
    for i in range(1, len(visual_types)):
        if visual_types[i] == visual_types[i - 1]:
            consecutive_same += 1
    if consecutive_same == 0 and len(scenes) > 3:
        strengths.append("Pillar 3 (Retention): No consecutive same-type scenes")
        retention_pillar += 10
    elif consecutive_same > 2:
        issues.append(f"Pillar 3 (Retention): {consecutive_same} consecutive same-type pairs — hurts pacing")
        retention_pillar -= 10

    # Meme count for pattern interrupts
    meme_count = sum(1 for v in visual_types if v == "meme_fullscreen")
    if 2 <= meme_count <= 4:
        strengths.append(f"Pillar 3 (Retention): {meme_count} meme moments — good humor density")
        retention_pillar += 10
    elif meme_count == 0:
        issues.append("Pillar 3 (Retention): No memes — add 2-3 humor beats")
        retention_pillar -= 5

    # Scene count
    if len(scenes) >= 12:
        strengths.append(f"Pillar 3 (Retention): {len(scenes)} scenes — good visual pacing")
        retention_pillar += 10
    elif len(scenes) < 8:
        issues.append(f"Pillar 3 (Retention): Only {len(scenes)} scenes — slideshow risk")
        retention_pillar -= 15

    # Duration sweet spot (4-6 min)
    if 240 <= audio_duration <= 360:
        strengths.append(f"Pillar 3 (Retention): Duration {audio_duration:.0f}s — optimal range")
        retention_pillar += 10
    elif audio_duration < 180:
        issues.append(f"Pillar 3 (Retention): Only {audio_duration:.0f}s — too short for watch time")
        retention_pillar -= 10

    retention_pillar = max(0, min(100, retention_pillar))

    # -----------------------------------------------------------------------
    # Pillar 4: THE ENGAGEMENT (Comments+Shares) — Does content spark action?
    # -----------------------------------------------------------------------
    engagement_pillar = 50  # base

    narration_lower = narration.lower()

    # Count opinions/hot takes (statements with "I think", "honestly", "look,")
    opinion_markers = ["i think", "honestly", "look,", "here's the thing", "hot take",
                       "my prediction", "i believe", "bet that", "unpopular opinion"]
    opinion_count = sum(1 for m in opinion_markers if m in narration_lower)
    if opinion_count >= 2:
        strengths.append(f"Pillar 4 (Engagement): {opinion_count} opinion moments — drives comments")
        engagement_pillar += 15
    elif opinion_count == 0:
        issues.append("Pillar 4 (Engagement): No clear opinions — content won't spark debate")
        engagement_pillar -= 10

    # Count predictions
    prediction_markers = ["predict", "will be", "going to", "bet that", "by 2", "next year",
                          "within", "expect", "my guess"]
    prediction_count = sum(1 for m in prediction_markers if m in narration_lower)
    if prediction_count >= 1:
        strengths.append("Pillar 4 (Engagement): Contains predictions — invites debate")
        engagement_pillar += 10

    # Count questions (rhetorical and direct)
    question_count = narration.count("?")
    if 2 <= question_count <= 5:
        strengths.append(f"Pillar 4 (Engagement): {question_count} questions — good engagement hooks")
        engagement_pillar += 10
    elif question_count == 0:
        issues.append("Pillar 4 (Engagement): No questions — add rhetorical questions")
        engagement_pillar -= 5
    elif question_count > 6:
        issues.append(f"Pillar 4 (Engagement): {question_count} questions — too many, feels interrogative")
        engagement_pillar -= 5

    # Check for controversial/contrarian takes
    contrarian_markers = ["wrong", "actually", "nobody's talking about", "everyone thinks",
                          "overrated", "underrated", "myth"]
    contrarian_count = sum(1 for m in contrarian_markers if m in narration_lower)
    if contrarian_count >= 1:
        strengths.append("Pillar 4 (Engagement): Contrarian angle — boosts shares")
        engagement_pillar += 10

    engagement_pillar = max(0, min(100, engagement_pillar))

    # -----------------------------------------------------------------------
    # Pillar 5: THE ALGORITHM (Session Time) — Does YouTube push it?
    # -----------------------------------------------------------------------
    algorithm_pillar = 50  # base

    # Duration check (4-6 min sweet spot for algorithm)
    if 240 <= audio_duration <= 360:
        strengths.append("Pillar 5 (Algorithm): Duration in algorithm sweet spot")
        algorithm_pillar += 15
    elif audio_duration < 120:
        issues.append("Pillar 5 (Algorithm): Under 2min — YouTube won't push shorts-length")
        algorithm_pillar -= 15
    elif audio_duration > 480:
        issues.append("Pillar 5 (Algorithm): Over 8min — risk of retention drop-off")
        algorithm_pillar -= 5

    # Scene count meets minimum
    if len(scenes) >= 10:
        algorithm_pillar += 10
    else:
        issues.append(f"Pillar 5 (Algorithm): Only {len(scenes)} scenes — increase to 10+")
        algorithm_pillar -= 5

    # Word count for content depth
    word_count = len(narration.split())
    if word_count >= 800:
        strengths.append(f"Pillar 5 (Algorithm): {word_count} words — substantial depth")
        algorithm_pillar += 10
    elif word_count < 500:
        issues.append(f"Pillar 5 (Algorithm): Only {word_count} words — thin content")
        algorithm_pillar -= 10

    # No generic outro (good for session time — end on content)
    bad_outros = ["thanks for watching", "like and subscribe", "hit the bell", "see you next time"]
    last_100 = narration[-200:].lower()
    if any(b in last_100 for b in bad_outros):
        issues.append("Pillar 5 (Algorithm): Generic outro detected — end on content instead")
        algorithm_pillar -= 10
    else:
        algorithm_pillar += 5

    algorithm_pillar = max(0, min(100, algorithm_pillar))

    # -----------------------------------------------------------------------
    # Combine pillar scores into virality prediction
    # -----------------------------------------------------------------------
    pillar_scores = {
        "hook": hook_pillar,
        "click": click_pillar,
        "retention": retention_pillar,
        "engagement": engagement_pillar,
        "algorithm": algorithm_pillar,
    }

    virality = int(
        hook_pillar * 0.25
        + click_pillar * 0.25
        + retention_pillar * 0.20
        + engagement_pillar * 0.15
        + algorithm_pillar * 0.15
    )
    virality = max(0, min(100, virality))

    # Frame file check
    missing_frames = [p for p in frame_paths if not os.path.exists(p)]
    if missing_frames:
        issues.append(f"{len(missing_frames)} frames missing from disk")

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

    # Generate recommendations based on weakest pillars
    weakest = min(pillar_scores, key=pillar_scores.get)
    if pillar_scores[weakest] < 60:
        pillar_recs = {
            "hook": "Strengthen opening — start with a surprising fact or bold claim",
            "click": "Improve title — add power words, numbers, or a curiosity gap",
            "retention": "Add visual variety — more frame types, memes, and scene changes",
            "engagement": "Add opinions, predictions, and questions to spark comments",
            "algorithm": "Adjust duration to 4-6 min and ensure content depth",
        }
        recommendations.append(f"Focus area: {pillar_recs[weakest]}")

    if "?" not in title:
        recommendations.append("Questions in titles can boost CTR")

    return {
        "virality_prediction": virality,
        "pillar_scores": pillar_scores,
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
    """Combine all QA results into a formatted report string with pillar breakdown."""
    lines = []
    lines.append(
        f"## QA Report — Grade: {video_review['overall_grade']} "
        f"(Virality: {video_review['virality_prediction']}/100)"
    )
    lines.append("")

    # Pillar-by-pillar breakdown
    pillar_scores = video_review.get("pillar_scores", {})
    if pillar_scores:
        lines.append("### Virality Pillars")
        pillar_labels = {
            "hook": "1. THE HOOK (First 5s)",
            "click": "2. THE CLICK (Title+Thumb)",
            "retention": "3. THE RETENTION (Keep Watching)",
            "engagement": "4. THE ENGAGEMENT (Comments)",
            "algorithm": "5. THE ALGORITHM (Session Time)",
        }
        for key, label in pillar_labels.items():
            score = pillar_scores.get(key, 0)
            bar_len = score // 5
            bar = "#" * bar_len + "-" * (20 - bar_len)
            grade = "A" if score >= 80 else "B" if score >= 65 else "C" if score >= 50 else "D" if score >= 35 else "F"
            lines.append(f"  {label}: [{bar}] {score}/100 ({grade})")
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
