import asyncio
import os
from datetime import datetime, timedelta

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


async def get_posts_from_board_by_date(page: Page, board_url: str, board_name: str, target_date: str, limit: int = 5) -> list[dict]:
    """
    특정 게시판에서 특정 날짜의 게시글 목록 가져오기

    Args:
        page: Playwright Page 객체
        board_url: 게시판 URL
        board_name: 게시판 이름
        target_date: 찾을 날짜 (YYYY.MM.DD 형식)
        limit: 가져올 최대 게시글 수

    Returns:
        list[dict]: 게시글 정보 리스트 (title, url, date)
    """
    try:
        print(f"\n'{board_name}' 게시판으로 이동 중...")

        # 게시판 페이지로 이동 (상대 경로를 절대 경로로 변환)
        if board_url.startswith("/"):
            board_url = f"https://cafe.naver.com{board_url}"

        await page.goto(board_url)
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(3000)

        print(f"찾을 날짜: {target_date}")

        posts = []

        # 새로운 카페 UI는 iframe 없이 직접 렌더링됨
        # iframe 존재 여부 확인
        iframe_exists = await page.locator("iframe#cafe_main").count() > 0

        if iframe_exists:
            print("iframe 모드로 게시글 검색 중...")
            # 구버전: iframe 내부에서 게시글 목록 찾기
            cafe_iframe = page.frame_locator("iframe#cafe_main")
            article_items = await cafe_iframe.locator("tr").all()
        else:
            print("일반 페이지 모드로 게시글 검색 중...")
            # 신버전: 메인 페이지에서 직접 게시글 목록 찾기
            article_items = await page.locator("tr").all()

        print(f"발견된 전체 행 수: {len(article_items)}")

        for item in article_items:
            # 이미 필요한 개수만큼 찾았으면 중단
            if len(posts) >= limit:
                break

            try:
                # 날짜 찾기 (작성일 컬럼) - 여러 선택자 시도
                date_text = ""
                try:
                    date_elem = item.locator("td.td_date, td[class*='date'], .date, td:has-text('2025')")
                    date_text = await date_elem.inner_text(timeout=100)
                except:
                    pass

                # 날짜 텍스트가 비어있으면 스킵
                if not date_text or date_text.strip() == "":
                    continue

                # 특정 날짜 게시글만 필터링 (YYYY.MM.DD 형식 매칭)
                if target_date in date_text:
                    # 제목 찾기
                    title = ""
                    post_url = ""
                    try:
                        title_elem = item.locator("a[href*='articles'], a[href*='Article']").first
                        title = await title_elem.inner_text(timeout=100)
                        post_url = await title_elem.get_attribute("href", timeout=100)
                    except:
                        pass

                    if title and post_url:
                        # 상대 경로를 절대 경로로 변환
                        if post_url.startswith("/"):
                            post_url = f"https://cafe.naver.com{post_url}"

                        posts.append({
                            "title": title.strip(),
                            "url": post_url,
                            "date": date_text.strip()
                        })
                        print(f"  ✓ [{date_text.strip()}] {title.strip()}")

            except Exception as e:
                # 제목이나 날짜가 없는 행은 무시
                continue

        print(f"'{board_name}'에서 찾은 게시글: {len(posts)}개")
        return posts

    except Exception as e:
        print(f"'{board_name}' 게시판에서 게시글 가져오기 중 오류 발생: {e}")
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
    # 오늘 날짜 (YYYY.MM.DD 형식)
    today = datetime.now().strftime("%Y.%m.%d")
    return await get_posts_from_board_by_date(page, board_url, board_name, today)


async def visit_post(page: Page, post_url: str, post_title: str) -> dict:
    """
    특정 게시글 방문하여 본문 내용 가져오기

    Args:
        page: Playwright Page 객체
        post_url: 게시글 URL
        post_title: 게시글 제목

    Returns:
        dict: 게시글 정보 (title, url, content)
    """
    try:
        print(f"\n게시글 방문 중: {post_title}")

        await page.goto(post_url)
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(2000)

        # 본문 내용 가져오기
        content = ""

        # iframe 존재 여부 확인
        iframe_exists = await page.locator("iframe#cafe_main").count() > 0

        if iframe_exists:
            print("  iframe 모드로 본문 추출 중...")
            # 구버전: iframe 내부에서 본문 찾기
            cafe_iframe = page.frame_locator("iframe#cafe_main")
            try:
                # 본문 영역 선택자 (다양한 선택자 시도)
                content_elem = cafe_iframe.locator(".se-main-container, .ArticleContentBox, div.article_viewer, #content").first
                content = await content_elem.inner_text(timeout=3000)
            except Exception as e:
                print(f"  iframe 본문 추출 실패: {e}")
        else:
            print("  일반 페이지 모드로 본문 추출 중...")
            # 신버전: 메인 페이지에서 직접 본문 찾기
            try:
                # 다양한 본문 선택자 시도
                selectors = [
                    ".se-main-container",  # 스마트에디터
                    ".article_viewer",  # 구버전 카페
                    "[class*='ArticleContent']",  # 새 카페 UI
                    "article",  # HTML5 article 태그
                    ".post_ct",  # 포스트 컨텐츠
                ]

                for selector in selectors:
                    try:
                        content_elem = page.locator(selector).first
                        content = await content_elem.inner_text(timeout=1000)
                        if content and content.strip():
                            print(f"  본문 추출 성공 (선택자: {selector})")
                            break
                    except:
                        continue

            except Exception as e:
                print(f"  본문 추출 실패: {e}")

        # 본문이 비어있으면 전체 페이지 텍스트 가져오기 시도
        if not content or not content.strip():
            print("  기본 선택자로 본문을 찾을 수 없어 전체 페이지에서 추출 시도...")
            try:
                content = await page.inner_text("body")
            except:
                content = ""

        content = content.strip()

        if content:
            print(f"✓ 게시글 로드 완료: {post_title} (본문 길이: {len(content)}자)")
        else:
            print(f"⚠ 게시글 로드 완료하였으나 본문을 찾을 수 없음: {post_title}")

        return {
            "title": post_title,
            "url": post_url,
            "content": content
        }

    except Exception as e:
        print(f"게시글 방문 중 오류 발생: {e}")
        return {
            "title": post_title,
            "url": post_url,
            "content": ""
        }


async def main():
    """메인 함수"""
    # 환경 변수에서 설정 가져오기
    cafe_url = os.getenv("CAFE_URL")
    naver_id = os.getenv("NAVER_ID")
    naver_pw = os.getenv("NAVER_PW")

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
        await page.goto("https://nid.naver.com/nidlogin.login")
        await page.wait_for_load_state("networkidle")

        # 자동 로그인 시도
        if naver_id and naver_pw:
            print("자동 로그인을 시도합니다...")

            # 아이디 입력
            await page.fill('input[name="id"]', naver_id)
            await page.wait_for_timeout(500)

            # 비밀번호 입력
            await page.fill('input[name="pw"]', naver_pw)
            await page.wait_for_timeout(500)

            # 로그인 버튼 클릭
            await page.click('button[type="submit"]')

            # 15초 대기
            print("로그인 처리 중... 15초 대기")
            for i in range(15, 0, -1):
                print(f"대기 중... ({i}초 남음)")
                await asyncio.sleep(1)

            print("로그인 완료!")
        else:
            print(".env 파일에 NAVER_ID와 NAVER_PW가 없습니다.")
            print("30초 안에 로그인을 완료해주세요...")
            # 30초 동안 사용자가 로그인하도록 대기
            for i in range(30, 0, -1):
                print(f"로그인 대기 중... ({i}초 남음)")
                await asyncio.sleep(1)

        print("\n카페로 이동합니다.")

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

        # 2일 전 날짜 계산 (YYYY.MM.DD 형식)
        two_days_ago = (datetime.now() - timedelta(days=2)).strftime("%Y.%m.%d")
        print(f"\n2일 전 날짜: {two_days_ago}")

        # 각 '진행' 게시판에서 2일 전 게시글 확인
        for board in jinhaeng_boards:
            print(f"\n{'='*60}")
            print(f"게시판: {board['name']}")
            print(f"{'='*60}")

            # 2일 전 게시글 5개 가져오기
            two_days_posts = await get_posts_from_board_by_date(page, board["url"], board["name"], two_days_ago, limit=5)

            if not two_days_posts:
                print(f"'{board['name']}'에 2일 전 작성된 게시글이 없습니다. 다음 게시판으로 이동합니다.")
                continue

            if len(two_days_posts) < 5:
                print(f"'{board['name']}'에 2일 전 게시글이 {len(two_days_posts)}개만 있습니다. (5개 미만) 다음 게시판으로 이동합니다.")
                continue

            print(f"\n2일 전 작성된 게시글: {len(two_days_posts)}개")

            # 각 게시글 방문하고 본문 수집
            post_contents = []
            for post in two_days_posts:
                post_data = await visit_post(page, post["url"], post["title"])
                post_contents.append(post_data)
                await page.wait_for_timeout(1000)  # 잠시 대기

            # 수집한 게시글 본문 출력
            print(f"\n\n{'='*60}")
            print(f"[{board['name']}] 수집된 게시글 본문")
            print(f"{'='*60}\n")

            for idx, post_data in enumerate(post_contents, 1):
                print(f"\n--- 게시글 {idx} ---")
                print(f"제목: {post_data['title']}")
                print(f"URL: {post_data['url']}")
                print(f"본문 길이: {len(post_data['content'])}자")
                print(f"\n[본문 내용]")
                print(post_data['content'][:500])  # 처음 500자만 출력
                if len(post_data['content']) > 500:
                    print(f"\n... (총 {len(post_data['content'])}자 중 500자만 표시)")
                print(f"\n{'='*60}")

        print("\n" + "="*60)
        print("모든 작업 완료! 브라우저를 수동으로 닫아주세요.")
        print("="*60)

        # 브라우저 자동 종료 비활성화 (사용자가 직접 닫음)
        # await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
