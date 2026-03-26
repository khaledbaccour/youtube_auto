"""Performance analysis engine — scores videos, generates insights, manages A/B tests."""

import os
import statistics

from database import (
    get_connection,
    insert_insight,
    insert_score,
    update_topic_performance,
)

# ---------------------------------------------------------------------------
# The 5 Virality Pillars
# ---------------------------------------------------------------------------
VIRALITY_PILLARS = """
1. THE HOOK (First 5s) — 30s retention. Does the opening grab attention immediately?
2. THE CLICK (Title+Thumbnail) — CTR. Does the packaging compel clicks from impressions?
3. THE RETENTION (Keep Watching) — avg view duration / total duration. Do viewers stay?
4. THE ENGAGEMENT (Comments+Shares) — (comments+likes)/views. Does content spark action?
5. THE ALGORITHM (Session Time) — subs_gained/views. Does YouTube's system push it?
"""

# ---------------------------------------------------------------------------
# Benchmarks (module-level, updatable)
# ---------------------------------------------------------------------------
BENCHMARKS = {
    "views_good": 500,
    "views_great": 2000,
    "ctr_good": 0.04,
    "ctr_great": 0.08,
    "retention_30s_good": 0.60,
    "retention_30s_great": 0.75,
    "avg_duration_good": 120,
}

# A/B test rotation order
AB_TEST_VARIABLES = [
    "hook_style",
    "visual_density",
    "topic_type",
    "tone",
    "meme_count",
    "script_pattern",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clamp(value, lo=0, hi=100):
    return max(lo, min(hi, value))


def _linear_score(value, good, great):
    """Map a value into 0-100 based on good (50) and great (90) thresholds."""
    if value is None or good == 0:
        return 50  # neutral default
    if value >= great:
        return 90 + _clamp(10 * (value - great) / max(great, 1), 0, 10)
    if value >= good:
        return 50 + 40 * (value - good) / max(great - good, 1)
    return _clamp(50 * value / max(good, 1), 0, 49)


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def _compute_title_score(title):
    """Heuristic title quality score (0-100)."""
    score = 0
    title_len = len(title)
    if 40 <= title_len <= 60:
        score += 30
    elif 30 <= title_len < 40 or 60 < title_len <= 70:
        score += 15
    if any(c.isdigit() for c in title):
        score += 20
    power_words = [
        "just", "breaking", "killed", "leaked", "secret", "finally",
        "biggest", "worst", "best", "new", "why", "how", "dead", "free",
    ]
    if any(w in title.lower() for w in power_words):
        score += 25
    if "?" in title:
        score += 15
    if title != title.upper():
        score += 10
    return _clamp(score)


def _compute_thumbnail_score(video_id):
    """Heuristic thumbnail quality score (0-100)."""
    conn = get_connection()
    row = conn.execute(
        "SELECT thumbnail_path FROM videos WHERE id = ?", (video_id,)
    ).fetchone()
    conn.close()
    path = row[0] if row and row[0] else None
    if not path or not os.path.exists(path):
        return 0
    score = 30  # exists
    size = os.path.getsize(path)
    if size > 100 * 1024:
        score += 20
    try:
        from PIL import Image
        img = Image.open(path)
        w, h = img.size
        if w >= 1280 and h >= 720:
            score += 25
        # Check if mostly white
        if img.mode in ("RGB", "RGBA"):
            pixels = list(img.getdata())
            sample = pixels[::max(1, len(pixels) // 500)]
            white_count = sum(1 for p in sample if all(c > 240 for c in p[:3]))
            if white_count / max(len(sample), 1) < 0.5:
                score += 25
    except Exception:
        pass
    return _clamp(score)


def _compute_description_score(video_id):
    """Heuristic description quality score (0-100)."""
    conn = get_connection()
    row = conn.execute(
        "SELECT description FROM videos WHERE id = ?", (video_id,)
    ).fetchone()
    conn.close()
    desc = (row[0] or "") if row else ""
    score = 0
    if len(desc) > 200:
        score += 30
    elif len(desc) > 100:
        score += 15
    if "00:" in desc or "timestamp" in desc.lower():
        score += 25
    keywords = ["ai", "model", "gpt", "claude", "google", "openai", "release", "update"]
    if any(k in desc.lower() for k in keywords):
        score += 25
    if "http" in desc:
        score += 20
    return _clamp(score)


def _compute_image_quality_score(video_id):
    """Heuristic image quality score based on cached images (0-100)."""
    images_dir = os.path.join("output", "images")
    if not os.path.isdir(images_dir):
        return 0
    files = [f for f in os.listdir(images_dir) if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))]
    if not files:
        return 0
    score = 0
    sizes = []
    for f in files:
        path = os.path.join(images_dir, f)
        sizes.append(os.path.getsize(path))
    avg_size = sum(sizes) / len(sizes)
    if avg_size > 100 * 1024:
        score += 25
    try:
        from PIL import Image
        all_large = True
        for f in files[:20]:  # sample up to 20
            img = Image.open(os.path.join(images_dir, f))
            if img.size[0] < 800 or img.size[1] < 600:
                all_large = False
                break
        if all_large:
            score += 25
    except Exception:
        pass
    # No watermark detection heuristic — assume clean if images passed QA
    score += 25
    # Variety of sources — check unique file sizes as proxy
    if len(set(s // 1024 for s in sizes)) >= min(len(sizes), 3):
        score += 25
    return _clamp(score)


def _compute_topic_score(video_id):
    """Score based on historical performance of this video's topic category (0-100)."""
    conn = get_connection()
    row = conn.execute(
        "SELECT topic_category FROM videos WHERE id = ?", (video_id,)
    ).fetchone()
    if not row or not row[0]:
        conn.close()
        return 50  # neutral
    category = row[0]
    # Get all categories ranked by avg_views
    rows = conn.execute(
        "SELECT topic_category, avg_views FROM topic_performance ORDER BY avg_views DESC"
    ).fetchall()
    conn.close()
    if not rows:
        return 50
    for i, r in enumerate(rows):
        if r[0] == category:
            # Rank-based score: top = 100, bottom = 0
            return _clamp(int(100 * (1 - i / max(len(rows) - 1, 1))))
    return 50


def score_video(video_id):
    """Compute and store pillar-based performance scores (0-100) for a video."""
    conn = get_connection()
    cur = conn.cursor()

    # Fetch latest analytics row for this video
    cur.execute(
        "SELECT views, avg_view_duration_seconds, ctr, likes, comments, "
        "retention_30s, retention_60s, retention_end, impressions, subs_gained "
        "FROM analytics WHERE video_id = ? ORDER BY date DESC LIMIT 1",
        (video_id,),
    )
    row = cur.fetchone()
    if not row:
        conn.close()
        return None

    views, avg_dur, ctr, likes, comments, ret_30, ret_60, ret_end, impressions, subs_gained = row
    views = views or 0
    likes = likes or 0
    comments = comments or 0
    subs_gained = subs_gained or 0

    # Fetch video metadata for title
    cur.execute("SELECT title FROM videos WHERE id = ?", (video_id,))
    vid_row = cur.fetchone()
    title = vid_row[0] if vid_row else ""

    # Fetch total video duration from video metadata (estimate from avg_dur if unavailable)
    # Use retention_end as a proxy: if someone watches 40% on average and avg_dur=120s, total ~300s
    total_duration = (avg_dur / ret_end) if (avg_dur and ret_end and ret_end > 0) else (avg_dur or 300)

    # -----------------------------------------------------------------------
    # Pillar 1: Hook (from analytics — 30s retention)
    # -----------------------------------------------------------------------
    hook_pillar = 0
    retention_30s = ret_30
    if retention_30s is not None:
        if retention_30s >= 0.75:
            hook_pillar = 100
        elif retention_30s >= 0.60:
            hook_pillar = 70
        else:
            hook_pillar = max(0, retention_30s / 0.60 * 70)

    # -----------------------------------------------------------------------
    # Pillar 2: Click (from analytics — CTR)
    # -----------------------------------------------------------------------
    click_pillar = 0
    ctr_val = ctr or 0
    if ctr_val >= 0.08:
        click_pillar = 100
    elif ctr_val >= 0.04:
        click_pillar = 70
    else:
        click_pillar = max(0, ctr_val / 0.04 * 70)

    # -----------------------------------------------------------------------
    # Pillar 3: Retention (from analytics — avg duration / total duration)
    # -----------------------------------------------------------------------
    retention_pillar = 0
    if avg_dur and total_duration:
        ratio = avg_dur / total_duration
        if ratio >= 0.60:
            retention_pillar = 100
        elif ratio >= 0.40:
            retention_pillar = 70
        else:
            retention_pillar = max(0, ratio / 0.40 * 70)

    # -----------------------------------------------------------------------
    # Pillar 4: Engagement (from analytics — (comments+likes)/views)
    # -----------------------------------------------------------------------
    engagement_pillar = 0
    if views > 0:
        eng_ratio = (comments + likes) / views
        if eng_ratio >= 0.05:
            engagement_pillar = 100
        elif eng_ratio >= 0.02:
            engagement_pillar = 70
        else:
            engagement_pillar = max(0, eng_ratio / 0.02 * 70)

    # -----------------------------------------------------------------------
    # Pillar 5: Algorithm (from analytics — subs_gained/views)
    # -----------------------------------------------------------------------
    algorithm_pillar = 0
    if views > 0:
        sub_ratio = subs_gained / views
        if sub_ratio >= 0.01:
            algorithm_pillar = 100
        elif sub_ratio >= 0.005:
            algorithm_pillar = 70
        else:
            algorithm_pillar = max(0, sub_ratio / 0.005 * 70)

    # -----------------------------------------------------------------------
    # Sub-scores (heuristic, from video metadata)
    # -----------------------------------------------------------------------
    title_score = _compute_title_score(title)
    thumbnail_score = _compute_thumbnail_score(video_id)
    description_score = _compute_description_score(video_id)
    image_quality_score = _compute_image_quality_score(video_id)
    topic_score = _compute_topic_score(video_id)
    workflow_score = 50  # default — updated by pipeline if validation/QA data available

    # -----------------------------------------------------------------------
    # Legacy scores (kept for backwards compat)
    # -----------------------------------------------------------------------
    hook_score = _clamp(int(hook_pillar))
    content_score = _clamp(int(0.5 * retention_pillar + 0.5 * engagement_pillar))
    visual_score = 50
    retention_points = [v for v in [ret_30, ret_60, ret_end] if v is not None]
    if len(retention_points) >= 2:
        variance = statistics.variance(retention_points)
        visual_score = _clamp(int(100 - variance * 1000))
    retention_score = _clamp(int(retention_pillar))
    virality_score = _clamp(int(
        0.25 * hook_pillar + 0.25 * click_pillar + 0.20 * retention_pillar
        + 0.15 * engagement_pillar + 0.15 * algorithm_pillar
    ))

    # -----------------------------------------------------------------------
    # Overall score (pillar-weighted)
    # -----------------------------------------------------------------------
    overall_score = _clamp(int(
        hook_pillar * 0.25
        + click_pillar * 0.25
        + retention_pillar * 0.20
        + engagement_pillar * 0.15
        + algorithm_pillar * 0.15
    ))

    notes = (
        f"views={views}, ctr={ctr_val}, avg_dur={avg_dur}s, "
        f"ret_30={ret_30}, ret_end={ret_end}, subs={subs_gained}, "
        f"pillars: hook={hook_pillar:.0f} click={click_pillar:.0f} "
        f"retention={retention_pillar:.0f} engagement={engagement_pillar:.0f} "
        f"algorithm={algorithm_pillar:.0f}"
    )

    scores_dict = {
        "hook_score": hook_score,
        "content_score": content_score,
        "visual_score": visual_score,
        "retention_score": retention_score,
        "virality_score": virality_score,
        "overall_score": overall_score,
        "hook_pillar_score": _clamp(int(hook_pillar)),
        "click_pillar_score": _clamp(int(click_pillar)),
        "retention_pillar_score": _clamp(int(retention_pillar)),
        "engagement_pillar_score": _clamp(int(engagement_pillar)),
        "algorithm_pillar_score": _clamp(int(algorithm_pillar)),
        "thumbnail_score": thumbnail_score,
        "title_score": title_score,
        "description_score": description_score,
        "image_quality_score": image_quality_score,
        "topic_score": topic_score,
        "workflow_score": workflow_score,
        "notes": notes,
    }
    insert_score(video_id, scores_dict)
    conn.close()

    return {"video_id": video_id, **scores_dict}


def analyze_hook_effectiveness():
    """Return hook styles ranked by average 30s retention."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT v.hook_style, AVG(a.retention_30s) AS avg_ret, COUNT(*) AS n "
        "FROM videos v JOIN analytics a ON v.id = a.video_id "
        "WHERE v.hook_style IS NOT NULL AND a.retention_30s IS NOT NULL "
        "GROUP BY v.hook_style "
        "ORDER BY avg_ret DESC"
    )
    results = [
        {"hook_style": r[0], "avg_retention_30s": round(r[1], 4), "sample_size": r[2]}
        for r in cur.fetchall()
    ]
    conn.close()
    return results


def analyze_topic_resonance():
    """Return topic categories ranked by average views + CTR."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT v.topic_category, AVG(a.views) AS avg_views, AVG(a.ctr) AS avg_ctr, COUNT(*) AS n "
        "FROM videos v JOIN analytics a ON v.id = a.video_id "
        "WHERE v.topic_category IS NOT NULL "
        "GROUP BY v.topic_category "
        "ORDER BY avg_views DESC"
    )
    results = [
        {
            "topic_category": r[0],
            "avg_views": round(r[1], 1),
            "avg_ctr": round(r[2], 4),
            "sample_size": r[3],
        }
        for r in cur.fetchall()
    ]
    conn.close()
    return results


def analyze_virality_factors():
    """Identify factors correlated with high virality scores."""
    conn = get_connection()
    cur = conn.cursor()

    factors = []

    # Topic category vs virality
    cur.execute(
        "SELECT v.topic_category, AVG(s.virality_score) AS avg_vir, COUNT(*) AS n "
        "FROM videos v JOIN scores s ON v.id = s.video_id "
        "WHERE v.topic_category IS NOT NULL AND s.virality_score IS NOT NULL "
        "GROUP BY v.topic_category HAVING n >= 2 "
        "ORDER BY avg_vir DESC"
    )
    for row in cur.fetchall():
        factors.append({
            "factor": f"topic_category={row[0]}",
            "correlation": round(row[1], 1),
            "sample_size": row[2],
        })

    # Hook style vs virality
    cur.execute(
        "SELECT v.hook_style, AVG(s.virality_score) AS avg_vir, COUNT(*) AS n "
        "FROM videos v JOIN scores s ON v.id = s.video_id "
        "WHERE v.hook_style IS NOT NULL AND s.virality_score IS NOT NULL "
        "GROUP BY v.hook_style HAVING n >= 2 "
        "ORDER BY avg_vir DESC"
    )
    for row in cur.fetchall():
        factors.append({
            "factor": f"hook_style={row[0]}",
            "correlation": round(row[1], 1),
            "sample_size": row[2],
        })

    # Title length buckets vs virality
    cur.execute(
        "SELECT "
        "  CASE "
        "    WHEN LENGTH(v.title) <= 40 THEN 'short' "
        "    WHEN LENGTH(v.title) <= 60 THEN 'medium' "
        "    ELSE 'long' "
        "  END AS title_bucket, "
        "  AVG(s.virality_score) AS avg_vir, COUNT(*) AS n "
        "FROM videos v JOIN scores s ON v.id = s.video_id "
        "WHERE s.virality_score IS NOT NULL "
        "GROUP BY title_bucket HAVING n >= 2 "
        "ORDER BY avg_vir DESC"
    )
    for row in cur.fetchall():
        factors.append({
            "factor": f"title_length={row[0]}",
            "correlation": round(row[1], 1),
            "sample_size": row[2],
        })

    # Script pattern vs virality
    cur.execute(
        "SELECT v.script_pattern, AVG(s.virality_score) AS avg_vir, COUNT(*) AS n "
        "FROM videos v JOIN scores s ON v.id = s.video_id "
        "WHERE v.script_pattern IS NOT NULL AND s.virality_score IS NOT NULL "
        "GROUP BY v.script_pattern HAVING n >= 2 "
        "ORDER BY avg_vir DESC"
    )
    for row in cur.fetchall():
        factors.append({
            "factor": f"script_pattern={row[0]}",
            "correlation": round(row[1], 1),
            "sample_size": row[2],
        })

    conn.close()
    return factors


def identify_ab_test_winners():
    """For each tested variable, determine which variant won."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT variable_tested, variant_value, control_value, winner "
        "FROM ab_tests WHERE winner IS NOT NULL"
    )
    rows = cur.fetchall()
    conn.close()

    # Group by variable
    groups = {}
    for variable, variant, control, winner in rows:
        groups.setdefault(variable, []).append({
            "variant": variant,
            "control": control,
            "winner": winner,
        })

    winners = []
    for variable, tests in groups.items():
        variant_wins = sum(1 for t in tests if t["winner"] == "variant")
        control_wins = sum(1 for t in tests if t["winner"] == "control")
        total = variant_wins + control_wins
        if total == 0:
            continue
        winner = "variant" if variant_wins >= control_wins else "control"
        margin = abs(variant_wins - control_wins) / total
        confidence = min(1.0, total / 10)  # more tests = higher confidence, cap at 1.0
        winners.append({
            "variable": variable,
            "winner": winner,
            "margin": round(margin, 2),
            "confidence": round(confidence, 2),
            "sample_size": total,
        })

    return winners


def generate_insights():
    """Run all analysis functions, produce and store human-readable insights."""
    insights = []

    # Hook effectiveness insights
    hooks = analyze_hook_effectiveness()
    if len(hooks) >= 2:
        best = hooks[0]
        worst = hooks[-1]
        if worst["avg_retention_30s"] > 0:
            ratio = round(best["avg_retention_30s"] / worst["avg_retention_30s"], 1)
            text = (
                f"{best['hook_style']} hooks average {best['avg_retention_30s']:.0%} 30s retention "
                f"vs {worst['avg_retention_30s']:.0%} for {worst['hook_style']} "
                f"({ratio}x, n={best['sample_size']}+{worst['sample_size']})"
            )
            confidence = min(1.0, (best["sample_size"] + worst["sample_size"]) / 12)
            insert_insight(text, "hook_analysis", round(confidence, 2), f"hook_styles: {len(hooks)}")
            insights.append(text)

    # Topic resonance insights
    topics = analyze_topic_resonance()
    if len(topics) >= 2:
        best = topics[0]
        worst = topics[-1]
        if worst["avg_views"] > 0:
            ratio = round(best["avg_views"] / worst["avg_views"], 1)
            text = (
                f"Videos about {best['topic_category']} get {ratio}x more views "
                f"than {worst['topic_category']} "
                f"(n={best['sample_size']}+{worst['sample_size']})"
            )
            confidence = min(1.0, (best["sample_size"] + worst["sample_size"]) / 12)
            insert_insight(text, "topic_analysis", round(confidence, 2), f"topic_categories: {len(topics)}")
            insights.append(text)

    # CTR insight
    if len(topics) >= 2:
        best_ctr = max(topics, key=lambda t: t["avg_ctr"])
        if best_ctr["avg_ctr"] > BENCHMARKS["ctr_good"]:
            text = (
                f"{best_ctr['topic_category']} topics have the highest CTR "
                f"at {best_ctr['avg_ctr']:.1%} (n={best_ctr['sample_size']})"
            )
            insert_insight(text, "ctr_analysis", round(min(1.0, best_ctr["sample_size"] / 6), 2), "")
            insights.append(text)

    # Virality factor insights
    virality_factors = analyze_virality_factors()
    if virality_factors:
        best_factor = virality_factors[0]
        if best_factor["correlation"] >= 60:
            text = (
                f"Highest virality factor: {best_factor['factor']} "
                f"(avg score {best_factor['correlation']}, n={best_factor['sample_size']})"
            )
            confidence = min(1.0, best_factor["sample_size"] / 8)
            insert_insight(text, "virality_analysis", round(confidence, 2), f"factors: {len(virality_factors)}")
            insights.append(text)

        # Find if any factor stands out significantly
        if len(virality_factors) >= 2:
            top = virality_factors[0]
            bottom = virality_factors[-1]
            gap = top["correlation"] - bottom["correlation"]
            if gap >= 15:
                text = (
                    f"{top['factor']} scores {gap:.0f} points higher in virality "
                    f"than {bottom['factor']} — strong signal"
                )
                confidence = min(1.0, (top["sample_size"] + bottom["sample_size"]) / 12)
                insert_insight(text, "virality_analysis", round(confidence, 2), "factor_gap")
                insights.append(text)

    # Pillar-based insights — identify weakest pillar across recent videos
    conn = get_connection()
    pillar_rows = conn.execute(
        "SELECT AVG(hook_pillar_score), AVG(click_pillar_score), AVG(retention_pillar_score), "
        "AVG(engagement_pillar_score), AVG(algorithm_pillar_score) "
        "FROM scores WHERE hook_pillar_score IS NOT NULL "
        "ORDER BY scored_at DESC LIMIT 10"
    ).fetchone()
    conn.close()
    if pillar_rows and pillar_rows[0] is not None:
        pillar_names = ["Hook", "Click", "Retention", "Engagement", "Algorithm"]
        pillar_avgs = list(pillar_rows)
        weakest_idx = pillar_avgs.index(min(pillar_avgs))
        strongest_idx = pillar_avgs.index(max(pillar_avgs))
        if pillar_avgs[strongest_idx] - pillar_avgs[weakest_idx] >= 15:
            text = (
                f"Weakest pillar: {pillar_names[weakest_idx]} "
                f"(avg {pillar_avgs[weakest_idx]:.0f}) vs strongest: "
                f"{pillar_names[strongest_idx]} (avg {pillar_avgs[strongest_idx]:.0f}) — "
                f"focus improvement on {pillar_names[weakest_idx]}"
            )
            insert_insight(text, "pillar_analysis", 0.7, "pillar_comparison")
            insights.append(text)

    # A/B test insights
    ab_winners = identify_ab_test_winners()
    for w in ab_winners:
        if w["confidence"] >= 0.3:
            text = (
                f"A/B test: {w['winner']} wins for {w['variable']} "
                f"(margin={w['margin']:.0%}, confidence={w['confidence']:.0%}, n={w['sample_size']})"
            )
            insert_insight(text, "ab_test", w["confidence"], f"variable: {w['variable']}")
            insights.append(text)

    return insights


def get_next_ab_test_variable():
    """Pick the least-recently-tested A/B variable and suggest variant/control values."""
    conn = get_connection()
    cur = conn.cursor()

    # Find most recent test date for each variable
    cur.execute(
        "SELECT variable_tested, MAX(v.created_at) AS last_tested "
        "FROM ab_tests t JOIN videos v ON t.video_id = v.id "
        "GROUP BY variable_tested"
    )
    tested = {r[0]: r[1] for r in cur.fetchall()}
    conn.close()

    # Pick the variable tested least recently (or never tested)
    variable = None
    oldest = None
    for v in AB_TEST_VARIABLES:
        last = tested.get(v)
        if last is None:
            variable = v
            break
        if oldest is None or last < oldest:
            oldest = last
            variable = v

    # Suggest variant/control based on variable
    variant_map = {
        "hook_style": {"variant": "contrarian", "control": "story_arc"},
        "visual_density": {"variant": "high", "control": "medium"},
        "topic_type": {"variant": "model_release", "control": "tool_comparison"},
        "tone": {"variant": "skeptical", "control": "neutral"},
        "meme_count": {"variant": "4", "control": "2"},
        "script_pattern": {"variant": "contrarian", "control": "story_arc"},
    }

    defaults = variant_map.get(variable, {"variant": "a", "control": "b"})
    return {
        "variable": variable,
        "variant": defaults["variant"],
        "control": defaults["control"],
    }


def refresh_topic_performance():
    """Recalculate topic_performance table from analytics data."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT v.topic_category, AVG(a.views), AVG(a.retention_30s), AVG(a.ctr), COUNT(*) "
        "FROM videos v JOIN analytics a ON v.id = a.video_id "
        "WHERE v.topic_category IS NOT NULL "
        "GROUP BY v.topic_category"
    )
    rows = cur.fetchall()
    conn.close()

    for category, avg_views, avg_retention, avg_ctr, sample_size in rows:
        update_topic_performance(
            category,
            round(avg_views, 1) if avg_views else 0,
            round(avg_retention, 4) if avg_retention else 0,
            round(avg_ctr, 4) if avg_ctr else 0,
            sample_size,
        )
