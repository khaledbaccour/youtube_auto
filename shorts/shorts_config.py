"""
Shorts pipeline configuration — constants, voice, caption style.
"""

import os
import sys

# Add parent dir so we can import from the main pipeline
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import CARTESIA_API_KEY

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

# Video dimensions (9:16 portrait)
WIDTH = 1080
HEIGHT = 1920
FPS = 30
TARGET_DURATION = 30  # seconds
MAX_DURATION = 60     # YouTube Shorts limit

# Cartesia TTS
CARTESIA_MODEL = "sonic"
CARTESIA_SAMPLE_RATE = 44100
SHORTS_VOICE_ID = os.environ.get("SHORTS_VOICE_ID", "")

# Caption style (word-by-word yellow text with grow effect)
CAPTION_FONT = "impact.ttf"
CAPTION_FONT_SIZE = 100
CAPTION_COLOR = "#FFD700"
CAPTION_STROKE_COLOR = "#000000"
CAPTION_STROKE_WIDTH = 4
CAPTION_Y_POSITION = 0.72  # 72% down from top
CAPTION_SCALE_START = 1.0
CAPTION_SCALE_END = 1.35

# Annotation style (red circles, arrows)
ANNOTATION_CIRCLE_COLOR = "#FF0000"
ANNOTATION_CIRCLE_WIDTH = 6

# Kokoro TTS fallback
KOKORO_MODEL_PATH = os.path.join(
    os.path.dirname(BASE_DIR), "assets", "models", "kokoro-v1.0.onnx"
)
KOKORO_VOICES_PATH = os.path.join(
    os.path.dirname(BASE_DIR), "assets", "models", "voices-v1.0.bin"
)
KOKORO_VOICE = "am_adam"
KOKORO_SPEED = 1.15

# Agent iteration limits
MAX_RESEARCH_ITERATIONS = 4
MAX_SCRIPT_ITERATIONS = 4
MIN_VIDEO_SCORE = 70
MIN_VIRALITY_SCORE = 75

# Niche configuration
NICHE = "ai_money"
NICHE_TOPICS = [
    "AI automation income proof 2026",
    "made money vibe coding",
    "faceless TikTok AI thousands dollars",
    "agentic AI business income",
    "AI agent made me money",
    "automated content creation income proof",
    "Claude AI money making method",
    "ChatGPT side hustle income proof",
    "AI tools passive income screen recording",
    "quit job AI automation income",
]
