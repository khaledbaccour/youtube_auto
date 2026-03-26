"""Deep analytics reporter — analyzes past video performance to guide future videos."""

import os
import json
from datetime import datetime
from config import OUTPUT_DIR
from database import get_connection

REPORT_PATH = os.path.join(OUTPUT_DIR, "analytics_report.json")


def generate_deep_analytics_report():
    """Query all video data, compute per-pillar analysis, identify what works/doesn't.
    Saves to output/analytics_report.json and returns the report dict."""
    conn = get_connection()

    # Get all videos with their scores and analytics
    videos = conn.execute("""
        SELECT v.*, s.hook_pillar_score, s.click_pillar_score, s.retention_pillar_score,
               s.engagement_pillar_score, s.algorithm_pillar_score, s.overall_score,
               s.virality_score, s.title_score, s.thumbnail_score,
               a.views, a.watch_time_minutes, a.avg_view_duration_seconds, a.ctr,
               a.likes, a.comments, a.subs_gained, a.impressions,
               a.retention_30s, a.retention_60s, a.retention_end
        FROM videos v
        LEFT JOIN scores s ON v.id = s.video_id
        LEFT JOIN analytics a ON v.id = a.video_id
        ORDER BY v.created_at DESC
    """).fetchall()
    conn.close()

    total = len(videos)
    if total == 0:
        report = _empty_report()
        _save_report(report)
        return report

    # Overall trends
    videos_with_views = [v for v in videos if v["views"] and v["views"] > 0]
    avg_views = sum(v["views"] for v in videos_with_views) / len(videos_with_views) if videos_with_views else 0
    avg_ctr = sum(v["ctr"] for v in videos_with_views if v["ctr"]) / max(1, sum(1 for v in videos_with_views if v["ctr"]))
    avg_ret_30s = sum(v["retention_30s"] for v in videos_with_views if v["retention_30s"]) / max(1, sum(1 for v in videos_with_views if v["retention_30s"]))

    best_video = max(videos_with_views, key=lambda v: v["views"]) if videos_with_views else None
    worst_video = min(videos_with_views, key=lambda v: v["views"]) if videos_with_views else None

    # Pillar analysis
    pillar_analysis = _analyze_pillars(videos)

    # What works / doesn't work
    what_works = _identify_what_works(videos)
    what_doesnt = _identify_what_doesnt_work(videos)

    # Recommendations
    recommendations = _generate_recommendations(pillar_analysis, what_works, what_doesnt)

    report = {
        "generated_at": datetime.now().isoformat(),
        "total_videos_analyzed": total,
        "videos_with_analytics": len(videos_with_views),
        "overall_trends": {
            "avg_views": round(avg_views, 1),
            "avg_ctr": round(avg_ctr, 4),
            "avg_retention_30s": round(avg_ret_30s, 3),
            "best_performing_video": {
                "title": best_video["title"] if best_video else "N/A",
                "views": best_video["views"] if best_video else 0,
                "topic": best_video["topic"] if best_video else "N/A",
            } if best_video else None,
            "worst_performing_video": {
                "title": worst_video["title"] if worst_video else "N/A",
                "views": worst_video["views"] if worst_video else 0,
                "topic": worst_video["topic"] if worst_video else "N/A",
            } if worst_video else None,
        },
        "pillar_analysis": pillar_analysis,
        "what_works": what_works,
        "what_doesnt_work": what_doesnt,
        "recommendations_for_next_video": recommendations,
    }

    _save_report(report)
    return report


def _analyze_pillars(videos):
    """Compute per-pillar averages and identify best/worst patterns."""
    scored = [v for v in videos if v["hook_pillar_score"] is not None]
    if not scored:
        return {p: {"avg_score": 0, "recommendation": "Not enough data yet"} for p in ["hook", "click", "retention", "engagement", "algorithm"]}

    def avg(field):
        vals = [v[field] for v in scored if v[field] is not None]
        return round(sum(vals) / len(vals), 1) if vals else 0

    # Group by hook_style for pillar 1 analysis
    hook_styles = {}
    for v in scored:
        style = v["hook_style"] or "unknown"
        if style not in hook_styles:
            hook_styles[style] = []
        if v["retention_30s"]:
            hook_styles[style].append(v["retention_30s"])

    best_hook = max(hook_styles.items(), key=lambda x: sum(x[1]) / max(1, len(x[1]))) if hook_styles else ("unknown", [])
    worst_hook = min(hook_styles.items(), key=lambda x: sum(x[1]) / max(1, len(x[1]))) if hook_styles else ("unknown", [])

    # Group by topic_category for pillar 2 analysis
    topic_cats = {}
    for v in scored:
        cat = v["topic_category"] or "unknown"
        if cat not in topic_cats:
            topic_cats[cat] = []
        if v["views"]:
            topic_cats[cat].append(v["views"])

    best_topic = max(topic_cats.items(), key=lambda x: sum(x[1]) / max(1, len(x[1]))) if topic_cats else ("unknown", [])

    return {
        "hook": {
            "avg_score": avg("hook_pillar_score"),
            "best_pattern": best_hook[0],
            "worst_pattern": worst_hook[0],
            "recommendation": f"Use {best_hook[0]} hooks — they average {sum(best_hook[1]) / max(1, len(best_hook[1])):.0%} 30s retention" if best_hook[1] else "Not enough data",
        },
        "click": {
            "avg_score": avg("click_pillar_score"),
            "avg_ctr": avg("ctr") if any(v["ctr"] for v in scored) else 0,
            "recommendation": "Titles with numbers and power words consistently get higher CTR" if avg("click_pillar_score") < 60 else "Click performance is solid",
        },
        "retention": {
            "avg_score": avg("retention_pillar_score"),
            "recommendation": "Increase visual variety and add more pattern interrupts" if avg("retention_pillar_score") < 60 else "Retention is healthy",
        },
        "engagement": {
            "avg_score": avg("engagement_pillar_score"),
            "recommendation": "Add stronger opinions and predictions to drive comments" if avg("engagement_pillar_score") < 50 else "Engagement is good",
        },
        "algorithm": {
            "avg_score": avg("algorithm_pillar_score"),
            "best_topic_category": best_topic[0],
            "recommendation": f"Focus on {best_topic[0]} topics — they get the most views" if best_topic[1] else "Not enough data",
        },
    }


def _identify_what_works(videos):
    """Identify patterns that correlate with high performance."""
    insights = []
    scored = [v for v in videos if v["views"] and v["views"] > 0]
    if len(scored) < 2:
        return ["Not enough data to identify patterns yet"]

    median_views = sorted(v["views"] for v in scored)[len(scored) // 2]

    # Title patterns
    titles_with_numbers = [v for v in scored if any(c.isdigit() for c in (v["title"] or ""))]
    titles_without = [v for v in scored if not any(c.isdigit() for c in (v["title"] or ""))]
    if titles_with_numbers and titles_without:
        avg_with = sum(v["views"] for v in titles_with_numbers) / len(titles_with_numbers)
        avg_without = sum(v["views"] for v in titles_without) / len(titles_without)
        if avg_with > avg_without * 1.2:
            insights.append(f"Titles with numbers get {avg_with / max(1, avg_without):.1f}x more views")

    # Hook style patterns
    hook_groups = {}
    for v in scored:
        style = v["hook_style"] or "unknown"
        hook_groups.setdefault(style, []).append(v["views"])
    if len(hook_groups) >= 2:
        best = max(hook_groups.items(), key=lambda x: sum(x[1]) / len(x[1]))
        insights.append(f"{best[0]} hooks average {sum(best[1]) / len(best[1]):.0f} views")

    # Topic patterns
    topic_groups = {}
    for v in scored:
        cat = v["topic_category"] or "unknown"
        topic_groups.setdefault(cat, []).append(v["views"])
    if len(topic_groups) >= 2:
        best = max(topic_groups.items(), key=lambda x: sum(x[1]) / len(x[1]))
        insights.append(f"{best[0]} topics perform best ({sum(best[1]) / len(best[1]):.0f} avg views)")

    return insights if insights else ["Not enough variation in data to identify patterns"]


def _identify_what_doesnt_work(videos):
    """Identify patterns that correlate with poor performance."""
    warnings = []
    scored = [v for v in videos if v["views"] and v["views"] > 0]
    if len(scored) < 2:
        return ["Not enough data yet"]

    # Low retention videos
    low_ret = [v for v in scored if v["retention_30s"] and v["retention_30s"] < 0.5]
    if low_ret:
        warnings.append(f"{len(low_ret)} videos had <50% 30s retention — weak hooks")

    # Low CTR videos
    low_ctr = [v for v in scored if v["ctr"] and v["ctr"] < 0.03]
    if low_ctr:
        warnings.append(f"{len(low_ctr)} videos had <3% CTR — titles/thumbnails need work")

    # Long videos that underperform
    long_vids = [v for v in scored if v["avg_view_duration_seconds"] and v["avg_view_duration_seconds"] > 420]
    if long_vids:
        avg_completion = sum(v["retention_end"] or 0 for v in long_vids) / len(long_vids)
        if avg_completion < 0.3:
            warnings.append("Videos over 7 minutes have low completion rates — keep to 4-6 min")

    return warnings if warnings else ["No clear failure patterns identified"]


def _generate_recommendations(pillar_analysis, what_works, what_doesnt):
    """Generate actionable recommendations for the next video."""
    recs = []

    # Weakest pillar gets priority
    pillar_scores = {k: v.get("avg_score", 0) for k, v in pillar_analysis.items()}
    weakest = min(pillar_scores, key=pillar_scores.get)
    recs.append(f"PRIORITY: Improve {weakest.upper()} pillar (currently {pillar_scores[weakest]:.0f}/100)")
    recs.append(pillar_analysis[weakest].get("recommendation", ""))

    # Add top what_works as reminders
    for insight in what_works[:2]:
        recs.append(f"Keep doing: {insight}")

    # Add top what_doesnt as warnings
    for warning in what_doesnt[:2]:
        recs.append(f"Avoid: {warning}")

    return recs


def _empty_report():
    """Return empty report when no data exists."""
    return {
        "generated_at": datetime.now().isoformat(),
        "total_videos_analyzed": 0,
        "videos_with_analytics": 0,
        "overall_trends": {"avg_views": 0, "avg_ctr": 0, "avg_retention_30s": 0},
        "pillar_analysis": {p: {"avg_score": 0, "recommendation": "No data yet"} for p in ["hook", "click", "retention", "engagement", "algorithm"]},
        "what_works": ["No data yet — first video will establish baseline"],
        "what_doesnt_work": ["No data yet"],
        "recommendations_for_next_video": ["Focus on all 5 virality pillars for the first video"],
    }


def _save_report(report):
    """Save report to JSON file."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"Analytics report saved to {REPORT_PATH}")


def load_analytics_report():
    """Load latest analytics report. Returns dict or empty report."""
    if os.path.exists(REPORT_PATH):
        with open(REPORT_PATH) as f:
            return json.load(f)
    return _empty_report()


def get_analytics_context_for_agents():
    """Format analytics report as text for agent prompts."""
    report = load_analytics_report()
    lines = ["## Past Video Analytics Report"]
    lines.append(f"Videos analyzed: {report['total_videos_analyzed']}")

    trends = report.get("overall_trends", {})
    lines.append(f"Avg views: {trends.get('avg_views', 0)}, Avg CTR: {trends.get('avg_ctr', 0):.1%}, Avg 30s retention: {trends.get('avg_retention_30s', 0):.0%}")

    lines.append("\n### What Works:")
    for item in report.get("what_works", []):
        lines.append(f"  + {item}")

    lines.append("\n### What Doesn't Work:")
    for item in report.get("what_doesnt_work", []):
        lines.append(f"  - {item}")

    lines.append("\n### Recommendations for Next Video:")
    for rec in report.get("recommendations_for_next_video", []):
        lines.append(f"  > {rec}")

    return "\n".join(lines)
