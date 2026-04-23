"""
財經新聞抓取模組
- RSS 訂閱源
- Google News RSS（台股關鍵字）
- 返回結構化新聞清單
"""
import feedparser
import requests
from datetime import datetime, timedelta
import re

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"

NEWS_QUERIES = [
    "台灣股市",
    "台積電 股票",
    "台股 半導體",
    "加權指數",
    "台股 週報",
]

def clean_html(text: str) -> str:
    """移除 HTML 標籤"""
    return re.sub(r'<[^>]+>', '', text or '').strip()

def fetch_google_news(query: str, max_items: int = 5) -> list:
    """透過 Google News RSS 抓取新聞"""
    url = GOOGLE_NEWS_RSS.format(query=requests.utils.quote(query))
    news_items = []
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries[:max_items]:
            published = entry.get('published', '')
            news_items.append({
                "title":     clean_html(entry.get('title', '')),
                "link":      entry.get('link', ''),
                "source":    entry.get('source', {}).get('title', 'Google News'),
                "published": published,
                "summary":   clean_html(entry.get('summary', ''))[:200],
            })
    except Exception as e:
        print(f"  [警告] 新聞抓取失敗 ({query}): {e}")
    return news_items

def fetch_company_news(company_name: str, max_items: int = 3) -> list:
    """抓取特定公司新聞"""
    return fetch_google_news(f"{company_name} 股票 台灣", max_items=max_items)

def fetch_market_news(max_total: int = 15) -> list:
    """抓取大盤市場新聞（去重）"""
    all_news = []
    seen_titles = set()
    for query in NEWS_QUERIES:
        items = fetch_google_news(query, max_items=5)
        for item in items:
            if item['title'] not in seen_titles:
                seen_titles.add(item['title'])
                all_news.append(item)
            if len(all_news) >= max_total:
                break
        if len(all_news) >= max_total:
            break
    return all_news[:max_total]

def fetch_all_news(companies: list) -> dict:
    """抓取大盤 + 各公司新聞"""
    print("  抓取市場新聞 ...")
    market_news = fetch_market_news()
    company_news = {}
    for c in companies:
        print(f"  抓取 {c['name']} 新聞 ...")
        company_news[c['symbol']] = fetch_company_news(c['name'])
    return {
        "market":  market_news,
        "company": company_news,
    }
