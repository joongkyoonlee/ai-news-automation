"""
AI 뉴스 수집/요약 자동화 파이프라인

흐름:
  1) RSS 피드에서 최신 AI 뉴스 수집
  2) OpenAI API로 한국어 요약 생성
  3) Markdown 보고서로 저장 (output/, obsidian/)
  4) Notion 데이터베이스에 저장 (선택)

환경변수:
  OPENAI_API_KEY      : OpenAI API 키 (필수)
  NOTION_TOKEN        : Notion Integration Token (선택)
  NOTION_DATABASE_ID  : Notion Database ID (선택)
  OBSIDIAN_API_KEY    : Obsidian Local REST API 키 (선택)
  OBSIDIAN_API_URL    : Obsidian Local REST API URL (선택)
"""

import os
import datetime
from pathlib import Path
from urllib.parse import quote

import feedparser
import requests
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
OBSIDIAN_DIR = Path(__file__).parent / "obsidian" / "AI News"


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


def save_obsidian_note(content: str) -> Path:
    """Obsidian에서 바로 읽을 수 있는 Markdown 노트로 저장한다."""
    OBSIDIAN_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.date.today().isoformat()
    path = OBSIDIAN_DIR / f"{today} AI 뉴스 브리핑.md"

    note = (
        "---\n"
        "type: ai-news\n"
        f"date: {today}\n"
        "tags:\n"
        "  - ai-news\n"
        "  - automation\n"
        "---\n\n"
        f"# AI 뉴스 브리핑 ({today})\n\n"
        f"{content}"
    )
    path.write_text(note, encoding="utf-8")
    print(f"[Obsidian] 노트 저장 완료 → {path}")
    return path


def publish_to_obsidian_api(note_path: Path, content: str) -> None:
    """Obsidian Local REST API가 설정되어 있으면 노트를 전송한다."""
    api_key = os.environ.get("OBSIDIAN_API_KEY")
    api_url = os.environ.get("OBSIDIAN_API_URL")

    if not api_key or not api_url:
        print("[Obsidian API] OBSIDIAN_API_KEY 또는 OBSIDIAN_API_URL이 없어 건너뜁니다.")
        return

    relative_path = note_path.relative_to(Path(__file__).parent)
    vault_path = quote(relative_path.as_posix(), safe="")
    url = f"{api_url.rstrip('/')}/vault/{vault_path}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "text/markdown",
    }
    response = requests.put(url, headers=headers, data=content.encode("utf-8"), timeout=30)
    if response.status_code >= 400:
        raise RuntimeError(
            f"Obsidian API 저장 실패: {response.status_code} {response.text}"
        )
    print("[Obsidian API] 노트 전송 완료")


def save_to_notion(content: str) -> None:
    """Notion 데이터베이스에 일일 브리핑 페이지를 생성한다."""
    notion_token = os.environ.get("NOTION_TOKEN")
    database_id = os.environ.get("NOTION_DATABASE_ID")

    if not notion_token or not database_id:
        print("[Notion] NOTION_TOKEN 또는 NOTION_DATABASE_ID가 없어 건너뜁니다.")
        return

    headers = {
        "Authorization": f"Bearer {notion_token}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }
    title_property = get_notion_title_property(database_id, headers)
    today = datetime.date.today().isoformat()
    title = f"AI 뉴스 브리핑 ({today})"
    url = "https://api.notion.com/v1/pages"
    payload = {
        "parent": {"database_id": database_id},
        "properties": {
            title_property: {
                "title": [
                    {
                        "text": {
                            "content": title,
                        }
                    }
                ]
            }
        },
        "children": markdown_to_notion_blocks(content),
    }

    response = requests.post(url, headers=headers, json=payload, timeout=30)
    if response.status_code >= 400:
        raise RuntimeError(
            f"Notion 저장 실패: {response.status_code} {response.text}"
        )
    print("[Notion] 페이지 저장 완료")


def get_notion_title_property(database_id: str, headers: dict) -> str:
    """데이터베이스에서 title 타입 속성 이름을 찾는다."""
    url = f"https://api.notion.com/v1/databases/{database_id}"
    response = requests.get(url, headers=headers, timeout=30)
    if response.status_code >= 400:
        raise RuntimeError(
            f"Notion 데이터베이스 조회 실패: {response.status_code} {response.text}"
        )

    properties = response.json().get("properties", {})
    for name, config in properties.items():
        if config.get("type") == "title":
            return name
    raise RuntimeError("Notion 데이터베이스에서 title 속성을 찾지 못했습니다.")


def markdown_to_notion_blocks(markdown: str) -> list[dict]:
    """Markdown 텍스트를 Notion paragraph 블록으로 단순 변환한다."""
    blocks = []
    for paragraph in split_text(markdown, max_length=1900):
        blocks.append(
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": paragraph,
                            },
                        }
                    ]
                },
            }
        )
    return blocks[:100]


def split_text(text: str, max_length: int) -> list[str]:
    """Notion rich_text 제한에 맞춰 긴 텍스트를 나눈다."""
    chunks = []
    current = ""
    for line in text.splitlines():
        candidate = f"{current}\n{line}".strip()
        if len(candidate) <= max_length:
            current = candidate
            continue
        if current:
            chunks.append(current)
        current = line
    if current:
        chunks.append(current)
    return chunks


# ── 메인 ──────────────────────────────────────────────
def main() -> None:
    articles = collect_news()
    if not articles:
        print("[종료] 수집된 기사가 없습니다.")
        return
    summary = summarize(articles)
    save_report(summary)
    obsidian_note_path = save_obsidian_note(summary)
    publish_to_obsidian_api(
        obsidian_note_path,
        obsidian_note_path.read_text(encoding="utf-8"),
    )
    save_to_notion(summary)


if __name__ == "__main__":
    main()
