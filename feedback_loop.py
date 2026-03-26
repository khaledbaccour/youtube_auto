"""Self-improving feedback loop — builds pipeline context from past performance and updates CLAUDE.md."""

import os
from datetime import datetime

from config import BASE_DIR
from database import (
    get_connection,
    get_recent_videos,
    get_top_performing_topics,
    get_unapplied_insights,
    insert_insight,
    mark_insight_applied,
)
from performance_analyzer import generate_insights, get_next_ab_test_variable

CLAUDE_MD_PATH = os.path.join(BASE_DIR, "CLAUDE.md")
INSIGHTS_SECTION_MARKER = "## 9. LEARNED INSIGHTS (Auto-Updated)"

# Maps weakest pillar to the CLAUDE.md section that should be improved
PILLAR_TO_SECTION = {
    "hook": "## 2. SCRIPT STRUCTURE RULES",
    "click": "## 6. YOUTUBE ALGORITHM OPTIMIZATION",
    "retention": "## 2. SCRIPT STRUCTURE RULES",
    "engagement": "## 3. CONTENT & ANALYSIS RULES",
    "algorithm": "## 6. YOUTUBE ALGORITHM OPTIMIZATION",
}


def _query_best_hook_style():
    """Find the hook style with the highest average 30s retention."""
    conn = get_connection()
    row = conn.execute(
        "SELECT v.hook_style FROM videos v "
        "JOIN analytics a ON v.id = a.video_id "
        "WHERE v.hook_style IS NOT NULL AND a.retention_30s IS NOT NULL "
        "GROUP BY v.hook_style ORDER BY AVG(a.retention_30s) DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return row["hook_style"] if row else "story_arc"


def _query_best_script_pattern():
    """Find the script pattern with the highest average overall score."""
    conn = get_connection()
    row = conn.execute(
        "SELECT v.script_pattern FROM videos v "
        "JOIN scores s ON v.id = s.video_id "
        "WHERE v.script_pattern IS NOT NULL "
        "GROUP BY v.script_pattern ORDER BY AVG(s.overall_score) DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return row["script_pattern"] if row else "story_arc"


def _get_pillar_averages():
    """Get average pillar scores across all scored videos."""
    conn = get_connection()
    row = conn.execute("""
        SELECT
            AVG(hook_pillar_score) as avg_hook,
            AVG(click_pillar_score) as avg_click,
            AVG(retention_pillar_score) as avg_retention,
            AVG(engagement_pillar_score) as avg_engagement,
            AVG(algorithm_pillar_score) as avg_algorithm,
            COUNT(*) as sample_size
        FROM scores
        WHERE hook_pillar_score IS NOT NULL
    """).fetchone()
    conn.close()
    if not row or row["sample_size"] == 0:
        return None
    return dict(row)


def _identify_weakest_pillar(averages):
    """Return the pillar name with the lowest average score."""
    if not averages:
        return None
    pillar_scores = {
        "hook": averages["avg_hook"] or 0,
        "click": averages["avg_click"] or 0,
        "retention": averages["avg_retention"] or 0,
        "engagement": averages["avg_engagement"] or 0,
        "algorithm": averages["avg_algorithm"] or 0,
    }
    return min(pillar_scores, key=pillar_scores.get)


def _generate_pillar_improvement_rule(weakest_pillar, avg_score):
    """Generate a targeted improvement rule for the weakest pillar."""
    today = datetime.now().strftime("%Y-%m-%d")
    rules = {
        "hook": (
            f"RULE ADDED [{today}]: Hook pillar avg is {avg_score:.0f}/100. "
            "Start every video with a surprising fact, statistic, or contrarian take. "
            "The first sentence must create a curiosity gap that demands the next 10 seconds."
        ),
        "click": (
            f"RULE ADDED [{today}]: Click pillar avg is {avg_score:.0f}/100. "
            "Titles must include a power word (killed, broke, leaked, exposed) and a number or specific noun. "
            "Avoid vague titles. Test: would YOU click this in a feed of 20 thumbnails?"
        ),
        "retention": (
            f"RULE ADDED [{today}]: Retention pillar avg is {avg_score:.0f}/100. "
            "Insert a pattern interrupt (visual change, tone shift, rhetorical question) every 45-60 seconds. "
            "No segment should feel like a lecture — break monologues with reactions."
        ),
        "engagement": (
            f"RULE ADDED [{today}]: Engagement pillar avg is {avg_score:.0f}/100. "
            "Every script must include at least 2 controversial but defensible opinions and 1 prediction "
            "that viewers will want to argue about in comments."
        ),
        "algorithm": (
            f"RULE ADDED [{today}]: Algorithm pillar avg is {avg_score:.0f}/100. "
            "Target 4-6 minute videos. End with an open question that drives comments. "
            "First 30 seconds must deliver enough value that viewers don't bounce."
        ),
    }
    return rules.get(weakest_pillar, "")


def _insert_rule_into_section(content, section_header, rule_text):
    """Insert a rule into a specific CLAUDE.md section, right after the header line."""
    if section_header not in content:
        # Section not found — append to end of insights section instead
        return content.rstrip() + "\n\n" + rule_text + "\n"

    idx = content.index(section_header)
    # Find end of the header line
    newline_after = content.find("\n", idx)
    if newline_after == -1:
        newline_after = len(content)

    # Insert rule after the section header line
    insert_text = f"\n\n> {rule_text}\n"
    return content[:newline_after] + insert_text + content[newline_after:]


def build_pipeline_context():
    """Query SQLite and return a dict of performance-based preferences for the pipeline."""
    top_topics = get_top_performing_topics(limit=5)
    preferred = [t["topic_category"] for t in top_topics[:3]] if top_topics else []
    avoid = [t["topic_category"] for t in top_topics[-2:]] if len(top_topics) >= 5 else []

    best_hook = _query_best_hook_style()
    best_pattern = _query_best_script_pattern()
    optimal_memes = 3  # default; updated by A/B test results over time

    ab_test = get_next_ab_test_variable()

    # Build insights summary string
    unapplied = get_unapplied_insights()
    insights_lines = [i["insight_text"] for i in unapplied[:10]] if unapplied else []
    insights_summary = "\n".join(f"- {line}" for line in insights_lines) if insights_lines else "No new insights yet."

    # Recent titles to avoid repetition
    recent = get_recent_videos(limit=10)
    recent_titles = [v["title"] for v in recent] if recent else []

    # Pillar averages
    pillar_avgs = _get_pillar_averages()

    return {
        "preferred_topic_types": preferred,
        "avoid_topic_types": avoid,
        "best_hook_style": best_hook,
        "best_script_pattern": best_pattern,
        "optimal_meme_count": optimal_memes,
        "ab_test": ab_test,
        "insights_summary": insights_summary,
        "recent_titles": recent_titles,
        "pillar_averages": pillar_avgs,
    }


def build_script_agent_prompt(context, topic):
    """Generate the system prompt for the Claude script-writer subagent."""
    from run_pipeline_agents import VIRALITY_PILLARS
    from virality_research import get_virality_context_for_agents

    # Read CLAUDE.md for base rules
    claude_md = ""
    if os.path.exists(CLAUDE_MD_PATH):
        with open(CLAUDE_MD_PATH, "r", encoding="utf-8") as f:
            claude_md = f.read()

    # Build performance guidance section
    perf_lines = []
    if context["preferred_topic_types"]:
        perf_lines.append(f"Top-performing topic types: {', '.join(context['preferred_topic_types'])}")
    if context["avoid_topic_types"]:
        perf_lines.append(f"Underperforming topic types (avoid unless strong angle): {', '.join(context['avoid_topic_types'])}")
    perf_lines.append(f"Best hook style so far: {context['best_hook_style']}")
    perf_lines.append(f"Best script pattern so far: {context['best_script_pattern']}")
    perf_lines.append(f"Optimal meme count: {context['optimal_meme_count']}")

    # A/B test instructions
    ab = context["ab_test"]
    ab_section = (
        f"\n## A/B TEST INSTRUCTION\n"
        f"This video is testing: **{ab['variable']}**\n"
        f"Use the **{ab['variant']}** variant (control would be: {ab['control']}).\n"
        f"Tag this video with variable_tested={ab['variable']}, variant_value={ab['variant']}."
    )

    # Recent titles to avoid
    titles_section = ""
    if context["recent_titles"]:
        titles_list = "\n".join(f"- {t}" for t in context["recent_titles"])
        titles_section = f"\n## RECENT TITLES (avoid repetition)\n{titles_list}\n"

    # Insights summary
    insights_section = f"\n## PERFORMANCE INSIGHTS\n{context['insights_summary']}\n"

    # Virality pillars + latest brief
    virality_context = get_virality_context_for_agents()

    # Analytics report (what works/doesn't from past videos)
    from analytics_reporter import get_analytics_context_for_agents
    analytics_context = get_analytics_context_for_agents()

    # Pillar score averages for the script-writer
    pillar_section = ""
    pillar_avgs = context.get("pillar_averages")
    if pillar_avgs and pillar_avgs.get("sample_size", 0) > 0:
        weakest = _identify_weakest_pillar(pillar_avgs)
        pillar_section = f"""
## PILLAR SCORE AVERAGES (from {pillar_avgs['sample_size']} scored videos)
- Hook: {pillar_avgs['avg_hook']:.0f}/100
- Click: {pillar_avgs['avg_click']:.0f}/100
- Retention: {pillar_avgs['avg_retention']:.0f}/100
- Engagement: {pillar_avgs['avg_engagement']:.0f}/100
- Algorithm: {pillar_avgs['avg_algorithm']:.0f}/100

**WEAKEST PILLAR: {weakest.upper()}** — Focus extra effort on improving this pillar in this script.
"""

    prompt = f"""You are a script writer for a Fireship-style AI/tech news YouTube channel.

## TOPIC
{topic}

## CHANNEL RULES
{claude_md}

{virality_context}

{analytics_context}

## PERFORMANCE-BASED PREFERENCES
{chr(10).join(perf_lines)}
{ab_section}
{titles_section}
{insights_section}
{pillar_section}

Write a script following the JSON schema in CLAUDE.md. The full_narration must be ONE continuous flowing text.
"""
    return prompt


def update_claude_md_insights():
    """Update CLAUDE.md with targeted pillar improvements and append unapplied insights to section 9."""
    if not os.path.exists(CLAUDE_MD_PATH):
        return 0

    with open(CLAUDE_MD_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    today = datetime.now().strftime("%Y-%m-%d")
    changes_made = 0

    # --- Step 1: Pillar-targeted improvements ---
    pillar_avgs = _get_pillar_averages()
    if pillar_avgs and pillar_avgs["sample_size"] >= 2:
        weakest = _identify_weakest_pillar(pillar_avgs)
        avg_score = pillar_avgs[f"avg_{weakest}"] or 0

        # Only add a rule if the weakest pillar is below 60
        if avg_score < 60:
            rule = _generate_pillar_improvement_rule(weakest, avg_score)
            section = PILLAR_TO_SECTION.get(weakest)

            # Check if this exact rule type was already added today (avoid duplicates)
            rule_marker = f"RULE ADDED [{today}]"
            if section and rule_marker not in content:
                content = _insert_rule_into_section(content, section, rule)
                changes_made += 1

                # Log the change as an insight
                evidence = (
                    f"weakest_pillar={weakest}, avg_score={avg_score:.1f}, "
                    f"sample_size={pillar_avgs['sample_size']}"
                )
                insert_insight(
                    f"Auto-rule added to {section}: {weakest} pillar improvement (avg {avg_score:.0f}/100)",
                    "pillar_improvement",
                    min(1.0, pillar_avgs["sample_size"] / 10),
                    evidence,
                )

    # --- Step 2: Append unapplied insights to section 9 ---
    unapplied = get_unapplied_insights()
    if unapplied:
        new_lines = []
        for insight in unapplied:
            confidence = insight.get("confidence", 0.5)
            text = insight["insight_text"]
            new_lines.append(f"- [{today}] {text} (confidence: {confidence})")

        new_block = "\n".join(new_lines)

        if INSIGHTS_SECTION_MARKER in content:
            marker_idx = content.index(INSIGHTS_SECTION_MARKER)
            rest = content[marker_idx + len(INSIGHTS_SECTION_MARKER):]
            next_section = rest.find("\n## ")
            if next_section == -1:
                content = content.rstrip() + "\n" + new_block + "\n"
            else:
                insert_pos = marker_idx + len(INSIGHTS_SECTION_MARKER) + next_section
                content = content[:insert_pos] + "\n" + new_block + content[insert_pos:]
        else:
            content = content.rstrip() + "\n\n---\n\n" + INSIGHTS_SECTION_MARKER + "\n\n" + new_block + "\n"

        for insight in unapplied:
            mark_insight_applied(insight["id"])

        changes_made += len(unapplied)

    # Write back if anything changed
    if changes_made > 0:
        with open(CLAUDE_MD_PATH, "w", encoding="utf-8") as f:
            f.write(content)

    return changes_made
