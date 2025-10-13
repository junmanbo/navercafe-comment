import asyncio
import os

from dotenv import load_dotenv
from playwright.async_api import Browser, Page, async_playwright

# .env 파일 로드
load_dotenv()


async def naver_login(page: Page, user_id: str, password: str) -> bool:
    """
    네이버 로그인 수행

    Args:
        page: Playwright Page 객체
        user_id: 네이버 아이디
        password: 네이버 비밀번호

    Returns:
        bool: 로그인 성공 여부
    """
    try:
        print("네이버 로그인 페이지로 이동 중...")
        await page.goto("https://nid.naver.com/nidlogin.login")

        # 아이디 입력
        print("아이디 입력 중...")
        await page.fill("#id", user_id)

        # 비밀번호 입력
        print("비밀번호 입력 중...")
        await page.fill("#pw", password)

        # 로그인 버튼 클릭
        print("로그인 버튼 클릭...")
        await page.click("#log\\.login")

        # 로그인 완료 대기 (메인 페이지로 이동 확인)
        await page.wait_for_load_state("networkidle")

        # 로그인 성공 여부 확인
        current_url = page.url
        if "naver.com" in current_url and "nidlogin" not in current_url:
            print("로그인 성공!")
            return True
        else:
            print("로그인 실패: 로그인 페이지에서 벗어나지 못했습니다.")
            return False

    except Exception as e:
        print(f"로그인 중 오류 발생: {e}")
        return False


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
    # 환경 변수에서 로그인 정보 가져오기
    naver_id = os.getenv("NAVER_ID")
    naver_pw = os.getenv("NAVER_PW")
    cafe_url = os.getenv("CAFE_URL")

    print(f"NAVER ID: {naver_id}")

    if not naver_id or not naver_pw:
        print(".env 파일에 NAVER_ID와 NAVER_PW를 설정해주세요.")
        print(".env.example 파일을 참고하여 .env 파일을 생성하세요.")
        return

    if not cafe_url:
        print(".env 파일에 CAFE_URL을 설정해주세요.")
        return

    async with async_playwright() as p:
        # 브라우저 실행 (headless=False로 설정하면 브라우저 창이 보임)
        print("브라우저 실행 중...")
        browser = await p.chromium.launch(
            headless=False,  # 디버깅을 위해 브라우저 창 표시
            slow_mo=100,  # 동작을 천천히 실행 (밀리초)
        )

        # 새 페이지 생성
        page = await browser.new_page()

        # 네이버 로그인
        success = await naver_login(page, naver_id, naver_pw)

        if success:
            print("\n로그인이 완료되었습니다.")

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

            print("\n브라우저를 10초 후 종료합니다...")
            await asyncio.sleep(10)

        # 브라우저 종료
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
