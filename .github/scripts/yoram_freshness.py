"""요람 PDF 신선도 유지 — 운영 자동화 계층 2.

docs/superpowers/specs/2026-08-24-운영-자동화-design.md 3.2장. www.ajou.ac.kr
요람/규정집 게시판(소프트웨어융합대학 카테고리, srCategoryId=355)에서 "소프트웨어학과"가
제목에 들어간 최신 연도 게시글을 찾아 PDF를 직접 다운로드한다.

robots.txt가 ClaudeBot·CCBot 등 AI 크롤러를 이름으로 차단하지만 User-agent: *는
허용한다 — 2026-08-24 사용자에게 이 사실을 공개하고 진행 승인을 받았다(기존
01_fetch_programs.py와 동일한 일반 UA 패턴, 연 1회뿐이라 부하 영향 없음).

사용법:
  python3 yoram_freshness.py check                  # 새 연도 있으면 "YYYY", 없으면 아무 출력 없음
  python3 yoram_freshness.py download <연도> <저장경로>  # 해당 연도 PDF를 저장경로에 다운로드
"""
import html
import re
import sys
import urllib.request
from pathlib import Path

BASE_URL = "https://www.ajou.ac.kr/kr/bachelor/bulletin.do"
LIST_URL = f"{BASE_URL}?mode=list&srCategoryId=355"
YORAM_DIR = Path(__file__).resolve().parent.parent.parent / "요람"

# 목록이 최신순 정렬이라 1페이지만 보면 된다(2026-08-24 실측 확인 — 1페이지에 이미
# 2026학년도가 있었음). 페이지네이션 순회는 하지 않는다.
TITLE_ROW_PATTERN = re.compile(r'<tr[^>]*>(.*?)</tr>', re.DOTALL)
TITLE_BOX_PATTERN = re.compile(r'<div class="b-title-box">(.*?)</div>', re.DOTALL)
SPAN_PATTERN = re.compile(r"<span>([^<]+)</span>")
DOWNLOAD_HREF_PATTERN = re.compile(r'href="(\?mode=download[^"]*)"')
YEAR_PATTERN = re.compile(r"(\d{4})학년도")


def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8")


def parse_software_dept_entries(list_html: str) -> list[dict]:
    """제목에 "소프트웨어학과"가 있는 게시글만 {year, title, download_path} 로 뽑는다."""
    entries = []
    for row in TITLE_ROW_PATTERN.findall(list_html):
        title_box_match = TITLE_BOX_PATTERN.search(row)
        if not title_box_match:
            continue
        span_match = SPAN_PATTERN.search(title_box_match.group(1))
        if not span_match:
            continue
        title = html.unescape(span_match.group(1)).strip()
        if "소프트웨어학과" not in title:
            continue
        year_match = YEAR_PATTERN.search(title)
        download_match = DOWNLOAD_HREF_PATTERN.search(row)
        if not year_match or not download_match:
            continue
        entries.append({
            "year": int(year_match.group(1)),
            "title": title,
            "download_path": html.unescape(download_match.group(1)),
        })
    return entries


def existing_years() -> set[int]:
    years = set()
    for pdf in YORAM_DIR.glob("*.pdf"):
        m = re.match(r"(\d{4})", pdf.stem)
        if m:
            years.add(int(m.group(1)))
    return years


def find_missing_latest_entry() -> dict | None:
    """게시판에서 소프트웨어학과 최신 연도를 찾아, 요람/ 폴더에 아직 없으면 그 항목을 돌려준다."""
    entries = parse_software_dept_entries(_fetch(LIST_URL))
    if not entries:
        return None
    latest = max(entries, key=lambda e: e["year"])
    if latest["year"] in existing_years():
        return None
    return latest


def download(download_path: str, dest: Path) -> None:
    req = urllib.request.Request(f"{BASE_URL}{download_path}", headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        dest.write_bytes(resp.read())


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2

    command = sys.argv[1]
    if command == "check":
        entry = find_missing_latest_entry()
        if entry:
            print(entry["year"])
        return 0

    if command == "download":
        if len(sys.argv) != 4:
            print("사용법: download <연도> <저장경로>", file=sys.stderr)
            return 2
        year = int(sys.argv[2])
        dest = Path(sys.argv[3])
        entries = parse_software_dept_entries(_fetch(LIST_URL))
        matches = [e for e in entries if e["year"] == year]
        if not matches:
            print(f"{year}학년도 소프트웨어학과 게시글을 찾지 못함", file=sys.stderr)
            return 1
        download(matches[0]["download_path"], dest)
        print(f"저장 완료: {dest} ({matches[0]['title']})")
        return 0

    print(f"알 수 없는 명령: {command}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
