import asyncio
import os
from datetime import datetime

from dotenv import load_dotenv
from playwright.async_api import Browser, Page, async_playwright

# .env 파일 로드
load_dotenv()


async def get_cafe_boards(page: Page) -> list[dict]:
    """
    카페 좌측 메뉴에서 게시판 목록 가져오기

    Args:
        page: Playwright Page 객체

    Returns:
        list[dict]: 게시판 정보 리스트 (name, url)
    """
    try:
        print("\n카페 게시판 목록 불러오는 중...")

        # iframe으로 전환 (네이버 카페는 iframe 구조 사용)
        await page.wait_for_timeout(2000)  # 페이지 로딩 대기

        # 좌측 메뉴의 게시판 링크들 찾기
        # 네이버 카페의 좌측 메뉴 구조를 탐색
        boards = []

        # iframe 내부로 전환
        cafe_iframe = page.frame_locator("iframe#cafe_main")

        # 좌측 메뉴의 게시판 링크 찾기
        menu_items = await page.locator("a.gm-tcol-c").all()

        print(f"\n발견된 메뉴 항목 수: {len(menu_items)}")

        for item in menu_items:
            try:
                name = await item.inner_text()
                href = await item.get_attribute("href")

                if name and href:
                    boards.append({
                        "name": name.strip(),
                        "url": href
                    })
                    print(f"  - {name.strip()}")
            except Exception as e:
                continue

        return boards

    except Exception as e:
        print(f"게시판 목록 불러오기 중 오류 발생: {e}")
        return []


async def get_today_posts_from_board(page: Page, board_url: str, board_name: str) -> list[dict]:
    """
    특정 게시판에서 오늘 날짜의 게시글 목록 가져오기

    Args:
        page: Playwright Page 객체
        board_url: 게시판 URL
        board_name: 게시판 이름

    Returns:
        list[dict]: 오늘 날짜 게시글 정보 리스트 (title, url, date)
    """
    try:
        print(f"\n'{board_name}' 게시판으로 이동 중...")

        # 게시판 페이지로 이동
        await page.goto(board_url)
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(1000)

        # 오늘 날짜 (MM.DD 형식)
        today = datetime.now().strftime("%m.%d")
        print(f"오늘 날짜: {today}")

        posts = []

        # iframe 내부에서 게시글 목록 찾기
        cafe_iframe = page.frame_locator("iframe#cafe_main")

        # 게시글 목록 테이블 찾기 (네이버 카페의 게시글 목록 구조)
        article_items = await cafe_iframe.locator("tr.article-board").all()

        if not article_items:
            # 다른 선택자 시도
            article_items = await cafe_iframe.locator("div.article-board").all()

        print(f"발견된 게시글 수: {len(article_items)}")

        for item in article_items:
            try:
                # 제목 찾기
                title_elem = item.locator("a.article-title, a.board-list")
                title = await title_elem.inner_text()
                post_url = await title_elem.get_attribute("href")

                # 날짜 찾기
                date_elem = item.locator("td.td_date, span.date")
                date_text = await date_elem.inner_text()

                # 오늘 날짜 게시글만 필터링
                if today in date_text:
                    posts.append({
                        "title": title.strip(),
                        "url": post_url,
                        "date": date_text.strip()
                    })
                    print(f"  ✓ [{date_text.strip()}] {title.strip()}")

            except Exception as e:
                continue

        return posts

    except Exception as e:
        print(f"'{board_name}' 게시판에서 게시글 가져오기 중 오류 발생: {e}")
        return []


async def visit_post(page: Page, post_url: str, post_title: str):
    """
    특정 게시글 방문

    Args:
        page: Playwright Page 객체
        post_url: 게시글 URL
        post_title: 게시글 제목
    """
    try:
        print(f"\n게시글 방문 중: {post_title}")

        await page.goto(post_url)
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(1000)

        print(f"✓ 게시글 로드 완료: {post_title}")

    except Exception as e:
        print(f"게시글 방문 중 오류 발생: {e}")


async def main():
    """메인 함수"""
    # 환경 변수에서 카페 URL 가져오기
    cafe_url = os.getenv("CAFE_URL")

    if not cafe_url:
        print(".env 파일에 CAFE_URL을 설정해주세요.")
        return

    async with async_playwright() as p:
        # Chromium 브라우저 실행
        print("Chromium 브라우저 실행 중...")
        browser = await p.chromium.launch(
            headless=False,  # 브라우저 창 표시
            slow_mo=100,  # 동작을 천천히 실행 (밀리초)
        )

        # 새 페이지 생성
        page = await browser.new_page()

        # 네이버 로그인 페이지로 이동
        print("\n네이버 로그인 페이지로 이동합니다.")
        print("30초 안에 로그인을 완료해주세요...")
        await page.goto("https://nid.naver.com/nidlogin.login")
        await page.wait_for_load_state("networkidle")

        # 30초 동안 사용자가 로그인하도록 대기
        for i in range(30, 0, -1):
            print(f"로그인 대기 중... ({i}초 남음)")
            await asyncio.sleep(1)

        print("\n로그인 시간 종료. 카페로 이동합니다.")

        # 카페 페이지로 이동
        print(f"\n카페로 이동 중: {cafe_url}")
        await page.goto(cafe_url)
        await page.wait_for_load_state("networkidle")

        # 게시판 목록 가져오기
        boards = await get_cafe_boards(page)

        if not boards:
            print("\n게시판을 찾을 수 없습니다.")
            return

        print(f"\n총 {len(boards)}개의 게시판을 발견했습니다.")

        # '진행'으로 시작하는 게시판 필터링
        jinhaeng_boards = [board for board in boards if board["name"].startswith("진행")]

        if not jinhaeng_boards:
            print("\n'진행'으로 시작하는 게시판이 없습니다.")
            return

        print(f"\n'진행'으로 시작하는 게시판: {len(jinhaeng_boards)}개")
        for board in jinhaeng_boards:
            print(f"  - {board['name']}")

        # 각 '진행' 게시판에서 오늘 날짜 게시글 확인
        for board in jinhaeng_boards:
            print(f"\n{'='*60}")
            print(f"게시판: {board['name']}")
            print(f"{'='*60}")

            # 오늘 날짜 게시글 가져오기
            today_posts = await get_today_posts_from_board(page, board["url"], board["name"])

            if not today_posts:
                print(f"'{board['name']}'에 오늘 작성된 게시글이 없습니다.")
                continue

            print(f"\n오늘 작성된 게시글: {len(today_posts)}개")

            # 각 게시글 방문
            for post in today_posts:
                await visit_post(page, post["url"], post["title"])
                await page.wait_for_timeout(1000)  # 잠시 대기

        print("\n" + "="*60)
        print("모든 작업 완료! 브라우저를 수동으로 닫아주세요.")
        print("="*60)

        # 브라우저 자동 종료 비활성화 (사용자가 직접 닫음)
        # await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
