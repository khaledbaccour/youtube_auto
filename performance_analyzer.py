"""Performance analysis engine — scores videos, generates insights, manages A/B tests."""

import statistics

from database import (
    get_connection,
    insert_insight,
    insert_score,
    update_topic_performance,
)

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

def score_video(video_id):
    """Compute and store performance scores (0-100) for a video."""
    conn = get_connection()
    cur = conn.cursor()

    # Fetch latest analytics row for this video
    cur.execute(
        "SELECT views, avg_view_duration_seconds, ctr, likes, comments, "
        "retention_30s, retention_60s, retention_end, impressions "
        "FROM analytics WHERE video_id = ? ORDER BY date DESC LIMIT 1",
        (video_id,),
    )
    row = cur.fetchone()
    if not row:
        conn.close()
        return None

    views, avg_dur, ctr, likes, comments, ret_30, ret_60, ret_end, impressions = row

    # Hook score — based on 30s retention
    hook_score = _clamp(int(_linear_score(
        ret_30 or 0,
        BENCHMARKS["retention_30s_good"],
        BENCHMARKS["retention_30s_great"],
    )))

    # Content score — avg view duration + comment engagement ratio
    dur_score = _linear_score(avg_dur or 0, BENCHMARKS["avg_duration_good"], BENCHMARKS["avg_duration_good"] * 2)
    comment_ratio = (comments or 0) / max(views, 1)
    engagement_score = min(100, comment_ratio * 2000)  # 5% comment rate -> 100
    content_score = _clamp(int(0.7 * dur_score + 0.3 * engagement_score))

    # Visual score — retention variance (smooth curve = good)
    retention_points = [v for v in [ret_30, ret_60, ret_end] if v is not None]
    if len(retention_points) >= 2:
        variance = statistics.variance(retention_points)
        # Low variance = smooth = good. Variance > 0.05 is choppy
        visual_score = _clamp(int(100 - variance * 1000))
    else:
        visual_score = 50

    # Retention score — end retention vs benchmark
    retention_score = _clamp(int(_linear_score(
        ret_end or 0,
        0.30,  # 30% end retention is decent
        0.50,  # 50% end retention is excellent
    )))

    # Virality score — composite of CTR, hook, engagement, growth (0-100)
    # CTR component (0-25)
    ctr_val = ctr or 0
    if ctr_val >= BENCHMARKS["ctr_great"]:
        ctr_component = 25
    elif ctr_val >= BENCHMARKS["ctr_good"]:
        ctr_component = 15
    else:
        ctr_component = int(25 * ctr_val / max(BENCHMARKS["ctr_good"], 0.001))

    # Hook component (0-25)
    ret_30_val = ret_30 or 0
    if ret_30_val >= BENCHMARKS["retention_30s_great"]:
        hook_component = 25
    elif ret_30_val >= BENCHMARKS["retention_30s_good"]:
        hook_component = 15
    else:
        hook_component = int(25 * ret_30_val / max(BENCHMARKS["retention_30s_good"], 0.001))

    # Engagement component (0-25) — (comments + likes) / views
    engagement_ratio = ((comments or 0) + (likes or 0)) / max(views, 1)
    engagement_component = _clamp(int(engagement_ratio * 500), 0, 25)  # 5% ratio -> 25

    # Growth component (0-25) — subs_gained / views
    cur.execute(
        "SELECT subs_gained FROM analytics WHERE video_id = ? ORDER BY date DESC LIMIT 1",
        (video_id,),
    )
    subs_row = cur.fetchone()
    subs_gained = (subs_row[0] or 0) if subs_row else 0
    growth_ratio = subs_gained / max(views, 1)
    growth_component = _clamp(int(growth_ratio * 2500), 0, 25)  # 1% ratio -> 25

    virality_score = _clamp(
        ctr_component + hook_component + engagement_component + growth_component, 0, 100
    )

    # Overall — weighted average (hook 25%, content 25%, visual 10%, retention 20%, virality 20%)
    overall_score = _clamp(int(
        0.25 * hook_score
        + 0.25 * content_score
        + 0.10 * visual_score
        + 0.20 * retention_score
        + 0.20 * virality_score
    ))

    notes = (
        f"views={views}, ctr={ctr}, avg_dur={avg_dur}s, "
        f"ret_30={ret_30}, ret_end={ret_end}, subs={subs_gained}"
    )

    scores_dict = {
        "hook_score": hook_score,
        "content_score": content_score,
        "visual_score": visual_score,
        "retention_score": retention_score,
        "virality_score": virality_score,
        "overall_score": overall_score,
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
