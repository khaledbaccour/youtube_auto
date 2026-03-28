"""
Longform baby niche pipeline configuration.
"""

import os
import sys

# Add parent dir so we can import from the main pipeline if needed
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

# Per-video archive — each completed video gets archived to videos/vN_topic/
# Previous outputs preserved for analysis. Current run always uses output/.
CURRENT_VIDEO = "v3"
VIDEOS_ARCHIVE_DIR = os.path.join(BASE_DIR, "videos")

# Video specs (16:9 landscape)
WIDTH = 1920
HEIGHT = 1080
FPS = 30
TARGET_DURATION_MINUTES = 11
TARGET_DURATION_S = TARGET_DURATION_MINUTES * 60  # 660s

# Niche
NICHE = "baby_psychology"
NICHE_DESCRIPTION = "Educational content about baby psychology, development, and behaviors"

# Visual style — flat cartoon illustration (reference video style)
# Warm beige backgrounds, clean thin outlines, flat color fills, minimal shading,
# educational annotations (arrows, labels, dashed lines), lots of negative space
VISUAL_STYLE = (
    "flat cartoon illustration, warm beige background, clean thin outlines, "
    "flat color fills, minimal shading, simple cute character design, "
    "educational annotations where relevant, lots of negative space, muted warm tones"
)
COLOR_PALETTE = {
    "primary_bg": "#FFF5E6",       # warm beige/cream (dominant background)
    "outline": "#5C4033",          # warm brown outlines
    "skin_tone": "#FDDCBD",       # soft peach skin
    "accent_blue": "#A8C8E8",     # dusty blue (clothing, arrows)
    "accent_green": "#B5D4B0",    # sage green (clothing, accents)
    "accent_pink": "#F5C2C7",     # muted pink (cheeks, accents)
    "accent_yellow": "#FFE5A0",   # soft yellow (clothing, highlights)
    "text_dark": "#333333",        # dark text for labels/annotations
    "text_label_bg": "#FFFFFF",    # white background for text labels
}

# TTS voice for longform (Cartesia Sonic)
LONGFORM_VOICE_ID = os.environ.get("LONGFORM_VOICE_ID", "")

# Reference video analysis (v3: mixed image + video, max 6 Veo3 clips)
REFERENCE_SCENE_COUNT = 41
REFERENCE_AVG_SCENE_DURATION_S = 16.1
IMAGE_SCENE_COUNT_TARGET = 35
VIDEO_SCENE_COUNT_TARGET = 6

# Scene types for visual rotation (never repeat back-to-back)
SCENE_TYPES = [
    "establishing_scene",        # nursery, home, park — wide cartoon shot
    "baby_expression",           # close-up baby face/reaction
    "parent_baby_interaction",   # parent holding, playing, watching baby
    "educational_diagram",       # cute infographic, brain diagram, milestone chart
    "detail_closeup",           # tiny hands, toys, objects, textures
]

# Remotion project path
REMOTION_DIR = os.path.join(BASE_DIR, "remotion")

# Agent iteration limits
MAX_TOPIC_ITERATIONS = 3
MAX_SCRIPT_ITERATIONS = 4
MAX_SCENE_ITERATIONS = 3

# Target word count for ~11 min at conversational pace (~150 wpm)
TARGET_WORD_COUNT_MIN = 1600
TARGET_WORD_COUNT_MAX = 1800

# Topic research patterns
TOPIC_PATTERNS = [
    "Why do babies {behavior}?",
    "What babies actually think when they {action}",
    "What happens inside a baby's brain when {event}",
    "How babies really learn to {skill}",
    "The science behind baby {phenomenon}",
    "What your baby is trying to tell you when they {behavior}",
    "The hidden reason babies {action}",
]

# Proven viral baby topics for research seeding
SEED_TOPICS = [
    "baby staring psychology meaning",
    "why babies smile at strangers",
    "baby brain development milestones",
    "why babies cry for no reason",
    "baby sleep science explained",
    "how babies learn language first words",
    "baby facial expressions meaning",
    "why babies laugh when tickled",
    "newborn reflexes explained science",
    "baby separation anxiety psychology",
]
