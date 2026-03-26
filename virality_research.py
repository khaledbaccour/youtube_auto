"""Virality brief management — save, load, and format virality research for agents."""
import os, json
from datetime import datetime
from config import OUTPUT_DIR
from run_pipeline_agents import VIRALITY_PILLARS

BRIEF_PATH = os.path.join(OUTPUT_DIR, "virality_brief.json")

def save_virality_brief(brief_dict):
    """Save virality brief to output/virality_brief.json with timestamp."""
    brief_dict["generated_at"] = datetime.now().isoformat()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(BRIEF_PATH, "w") as f:
        json.dump(brief_dict, f, indent=2)
    print(f"Virality brief saved to {BRIEF_PATH}")

def load_virality_brief():
    """Load latest virality brief. Returns dict or empty dict if none exists."""
    if os.path.exists(BRIEF_PATH):
        with open(BRIEF_PATH) as f:
            return json.load(f)
    return {}

def get_virality_context_for_agents():
    """Format the 5 pillars + latest brief as text for agent prompts."""
    context = VIRALITY_PILLARS + "\n"
    brief = load_virality_brief()
    if brief:
        context += "## Latest Virality Research Brief\n"
        context += json.dumps(brief, indent=2)
    return context

def print_brief():
    """Print current brief for agent consumption."""
    print(get_virality_context_for_agents())
