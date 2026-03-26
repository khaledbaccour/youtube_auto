"""Self-improving feedback loop — builds pipeline context from past performance and updates CLAUDE.md."""

import os
from datetime import datetime

from config import BASE_DIR
from database import (
    get_recent_videos,
    get_top_performing_topics,
    get_unapplied_insights,
    mark_insight_applied,
)
from performance_analyzer import generate_insights, get_next_ab_test_variable

CLAUDE_MD_PATH = os.path.join(BASE_DIR, "CLAUDE.md")
INSIGHTS_SECTION_MARKER = "## 9. LEARNED INSIGHTS (Auto-Updated)"


def _query_best_hook_style():
    """Find the hook style with the highest average 30s retention."""
    from database import get_connection
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
    from database import get_connection
    conn = get_connection()
    row = conn.execute(
        "SELECT v.script_pattern FROM videos v "
        "JOIN scores s ON v.id = s.video_id "
        "WHERE v.script_pattern IS NOT NULL "
        "GROUP BY v.script_pattern ORDER BY AVG(s.overall_score) DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return row["script_pattern"] if row else "story_arc"


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

    return {
        "preferred_topic_types": preferred,
        "avoid_topic_types": avoid,
        "best_hook_style": best_hook,
        "best_script_pattern": best_pattern,
        "optimal_meme_count": optimal_memes,
        "ab_test": ab_test,
        "insights_summary": insights_summary,
        "recent_titles": recent_titles,
    }


def build_script_agent_prompt(context, topic):
    """Generate the system prompt for the Claude script-writer subagent."""
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

    prompt = f"""You are a script writer for a Fireship-style AI/tech news YouTube channel.

## TOPIC
{topic}

## CHANNEL RULES
{claude_md}

## PERFORMANCE-BASED PREFERENCES
{chr(10).join(perf_lines)}
{ab_section}
{titles_section}
{insights_section}

Write a script following the JSON schema in CLAUDE.md. The full_narration must be ONE continuous flowing text.
"""
    return prompt


def update_claude_md_insights():
    """Append new unapplied insights to CLAUDE.md section 9 and mark them as applied."""
    unapplied = get_unapplied_insights()
    if not unapplied:
        return 0

    # Read current CLAUDE.md
    if not os.path.exists(CLAUDE_MD_PATH):
        return 0

    with open(CLAUDE_MD_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    today = datetime.now().strftime("%Y-%m-%d")

    # Format new insight lines
    new_lines = []
    for insight in unapplied:
        confidence = insight.get("confidence", 0.5)
        text = insight["insight_text"]
        new_lines.append(f"- [{today}] {text} (confidence: {confidence})")

    new_block = "\n".join(new_lines)

    # Find or create the insights section
    if INSIGHTS_SECTION_MARKER in content:
        # Append after existing section content
        marker_idx = content.index(INSIGHTS_SECTION_MARKER)
        # Find the next section header (## ) or end of file
        rest = content[marker_idx + len(INSIGHTS_SECTION_MARKER):]
        next_section = rest.find("\n## ")
        if next_section == -1:
            # Append at end
            content = content.rstrip() + "\n" + new_block + "\n"
        else:
            insert_pos = marker_idx + len(INSIGHTS_SECTION_MARKER) + next_section
            content = content[:insert_pos] + "\n" + new_block + content[insert_pos:]
    else:
        # Create section at end of file
        content = content.rstrip() + "\n\n---\n\n" + INSIGHTS_SECTION_MARKER + "\n\n" + new_block + "\n"

    with open(CLAUDE_MD_PATH, "w", encoding="utf-8") as f:
        f.write(content)

    # Mark all as applied
    for insight in unapplied:
        mark_insight_applied(insight["id"])

    return len(unapplied)
