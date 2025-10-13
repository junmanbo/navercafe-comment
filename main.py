import asyncio
import os

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

        # 카페 페이지로 이동
        print(f"\n카페로 이동 중: {cafe_url}")
        await page.goto(cafe_url)
        await page.wait_for_load_state("networkidle")

        # 게시판 목록 가져오기
        boards = await get_cafe_boards(page)

        if boards:
            print(f"\n총 {len(boards)}개의 게시판을 발견했습니다.")
        else:
            print("\n게시판을 찾을 수 없습니다.")

        print("\n작업 완료! 브라우저를 수동으로 닫아주세요.")

        # 브라우저 자동 종료 비활성화 (사용자가 직접 닫음)
        # await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
