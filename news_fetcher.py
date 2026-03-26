import feedparser
import requests
import html
import re
from datetime import datetime, timezone


# Working Google Trends RSS endpoint
GOOGLE_TRENDS_RSS = "https://trends.google.com/trending/rss?geo=US"

# Google News AI/tech RSS
GOOGLE_NEWS_AI_RSS = (
    "https://news.google.com/rss/search?"
    "q=artificial+intelligence+OR+AI+OR+machine+learning"
    "&hl=en-US&gl=US&ceid=US:en"
)

# AI/tech keywords for filtering
TECH_KEYWORDS = [
    'ai', 'gpt', 'claude', 'openai', 'google', 'apple', 'meta',
    'microsoft', 'nvidia', 'tesla', 'robot', 'chatbot', 'llm',
    'machine learning', 'deepseek', 'gemini', 'copilot', 'sora',
    'anthropic', 'midjourney', 'stable diffusion', 'samsung',
    'iphone', 'android', 'crypto', 'bitcoin', 'blockchain',
    'spacex', 'neuralink', 'chip', 'semiconductor', 'quantum',
]


def get_trending_ai_topic():
    """Find today's hottest AI/tech trending topic from Google Trends US.

    Returns:
        dict with keys: topic, source
    """
    try:
        from pytrends.request import TrendReq
        pytrends = TrendReq(hl='en-US', tz=360)
        trending = pytrends.trending_searches(pn='united_states')

        # Filter for tech/AI topics first
        for _, row in trending.iterrows():
            topic = row[0].lower()
            if any(kw in topic for kw in TECH_KEYWORDS):
                return {"topic": row[0], "source": "Google Trends US"}

        # Fallback: return #1 trending topic anyway
        return {"topic": trending.iloc[0, 0], "source": "Google Trends US (top trending)"}

    except Exception:
        # pytrends failed — try the RSS fallback
        return _get_trending_via_rss()


def _get_trending_via_rss():
    """Fallback: scrape Google Trends via RSS endpoint."""
    try:
        r = requests.get(
            GOOGLE_TRENDS_RSS,
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        if r.status_code == 200:
            feed = feedparser.parse(r.text)
            entries = feed.entries

            # Try to find a tech/AI match
            for entry in entries:
                title = entry.get("title", "")
                if any(kw in title.lower() for kw in TECH_KEYWORDS):
                    return {"topic": title, "source": "Google Trends US (RSS)"}

            # No tech match — return #1 trending
            if entries:
                return {
                    "topic": entries[0].get("title", "Unknown"),
                    "source": "Google Trends US (RSS, top trending)",
                }
    except Exception:
        pass

    # Last resort: pull top story from Google News AI feed
    return _get_top_news_topic()


def _get_top_news_topic():
    """Last-resort fallback: grab the top AI news headline as the topic."""
    try:
        feed = feedparser.parse(GOOGLE_NEWS_AI_RSS)
        if feed.entries:
            title = feed.entries[0].get("title", "AI news")
            # Strip source suffix (e.g., " - Reuters")
            topic = re.split(r"\s+-\s+", title)[0].strip()
            return {"topic": topic, "source": "Google News AI (fallback)"}
    except Exception:
        pass
    return {"topic": "AI industry developments", "source": "fallback"}


def fetch_ai_news(max_articles=10):
    """Fetch latest AI/tech news from Google News RSS.

    Returns:
        list of article dicts with keys: title, summary, source, link, published
    """
    feed = feedparser.parse(GOOGLE_NEWS_AI_RSS)

    articles = []
    for entry in feed.entries[:max_articles]:
        summary = re.sub(r"<[^>]+>", "", entry.get("summary", ""))
        summary = html.unescape(summary).strip()
        summary = summary.split("\n")[0].strip()

        published = None
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)

        articles.append({
            "title": entry.get("title", ""),
            "summary": summary,
            "link": entry.get("link", ""),
            "source": entry.get("source", {}).get("title", "Unknown"),
            "published": published,
        })

    return articles


def get_top_story():
    """Get today's biggest AI/tech news story."""
    articles = fetch_ai_news(max_articles=20)
    if not articles:
        return None
    return articles[0]


def get_trending_ai_topic_guided(preferred_categories=None, avoid_categories=None, recent_titles=None):
    """Enhanced topic fetcher that uses performance data to prefer certain topic types.

    Gets multiple candidate topics, scores them against preferences,
    avoids topics too similar to recent_titles, returns best match.
    """
    # Get base topic from existing function
    base_topic = get_trending_ai_topic()

    # For now, return base topic with category metadata
    # As more data accumulates, this will filter/rank candidates
    topic = base_topic
    if isinstance(topic, dict):
        topic["preferred_categories"] = preferred_categories or []
        topic["avoid_categories"] = avoid_categories or []
    return topic


if __name__ == "__main__":
    print("Finding today's trending AI/tech topic...\n")
    topic = get_trending_ai_topic()
    print(f"Topic:  {topic['topic']}")
    print(f"Source: {topic['source']}")

    print("\n--- Top 5 AI news headlines ---")
    articles = fetch_ai_news(5)
    for i, article in enumerate(articles, 1):
        pub = article["published"].strftime("%Y-%m-%d %H:%M") if article["published"] else "Unknown"
        print(f"{i}. [{pub}] {article['title']}")
        print(f"   Source: {article['source']}")
        print(f"   {article['summary'][:150]}...")
        print()
