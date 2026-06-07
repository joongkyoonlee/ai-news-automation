"""
AI 뉴스 수집/요약 자동화 파이프라인

흐름:
  1) RSS 피드에서 최신 AI 뉴스 수집
  2) Claude API로 한국어 요약 생성
  3) Markdown 보고서로 저장 (output/)

환경변수:
  OPENAI_API_KEY : OpenAI API 키 (필수)
"""

import os
import datetime
from pathlib import Path

import feedparser
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# ── 설정 ──────────────────────────────────────────────
# 수집할 RSS 피드 목록
RSS_FEEDS = [
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://www.theverge.com/rss/index.xml",
    "https://venturebeat.com/category/ai/feed/",
]

MAX_ITEMS_PER_FEED = 5          # 피드당 최대 기사 수
MODEL = "gpt-4o"                 # 요약에 사용할 모델
OUTPUT_DIR = Path(__file__).parent / "output"


# ── 1) 뉴스 수집 ──────────────────────────────────────
def collect_news() -> list[dict]:
    """RSS 피드에서 최신 기사를 수집한다."""
    articles = []
    for url in RSS_FEEDS:
        feed = feedparser.parse(url)
        source = feed.feed.get("title", url)
        for entry in feed.entries[:MAX_ITEMS_PER_FEED]:
            articles.append(
                {
                    "source": source,
                    "title": entry.get("title", "(제목 없음)"),
                    "link": entry.get("link", ""),
                    "summary": entry.get("summary", ""),
                }
            )
    print(f"[수집] 총 {len(articles)}개 기사 수집 완료")
    return articles


# ── 2) 요약 생성 ──────────────────────────────────────
def summarize(articles: list[dict]) -> str:
    """OpenAI API로 수집한 기사들을 한국어로 요약한다."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("환경변수 OPENAI_API_KEY 가 설정되지 않았습니다.")

    client = OpenAI(api_key=api_key)

    # 기사 목록을 프롬프트용 텍스트로 변환
    items = "\n\n".join(
        f"- [{a['source']}] {a['title']}\n  링크: {a['link']}\n  내용: {a['summary'][:500]}"
        for a in articles
    )

    prompt = (
        "아래는 오늘 수집한 AI 관련 뉴스 목록입니다.\n"
        "한국어로 핵심만 정리한 일일 AI 뉴스 브리핑을 Markdown으로 작성해 주세요.\n"
        "각 뉴스는 한 줄 요약 + 출처 링크를 포함하고, 마지막에 '오늘의 인사이트' 섹션을 추가하세요.\n\n"
        f"{items}"
    )

    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content


# ── 3) 보고서 저장 ────────────────────────────────────
def save_report(content: str) -> Path:
    """요약 결과를 날짜별 Markdown 파일로 저장한다."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.date.today().isoformat()
    path = OUTPUT_DIR / f"ai-news-{today}.md"

    header = f"# AI 뉴스 브리핑 ({today})\n\n"
    path.write_text(header + content, encoding="utf-8")
    print(f"[저장] 보고서 저장 완료 → {path}")
    return path


# ── 메인 ──────────────────────────────────────────────
def main() -> None:
    articles = collect_news()
    if not articles:
        print("[종료] 수집된 기사가 없습니다.")
        return
    summary = summarize(articles)
    save_report(summary)


if __name__ == "__main__":
    main()
