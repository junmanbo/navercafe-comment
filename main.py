import asyncio
import os
from datetime import datetime, timedelta

from dotenv import load_dotenv
from playwright.async_api import Browser, Page, async_playwright
from openai import OpenAI

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
                        # 제목에 '공지'가 포함된 게시글은 제외
                        if '공지' in title:
                            print(f"  ⊗ [{date_text.strip()}] {title.strip()} (공지 게시글 제외)")
                            continue

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

def get_user_confirmation(comment_text: str) -> bool:
    """
    사용자에게 댓글 등록 확인 받기

    Args:
        comment_text: 등록할 댓글 내용

    Returns:
        bool: 등록 승인 여부 (Y: True, N: False)
    """
    print("\n" + "="*60)
    print("[생성된 댓글 내용]")
    print(f"\"{comment_text}\"")
    print("="*60)

    while True:
        response = input("\n정말 이 댓글로 등록하시겠습니까? [Y/N]: ").strip().upper()

        if response == 'Y':
            print("✓ 댓글 등록을 진행합니다.")
            return True
        elif response == 'N':
            print("✗ 댓글 등록을 건너뜁니다. 다음 게시글로 이동합니다.")
            return False
        else:
            print("⚠ 잘못된 입력입니다. Y 또는 N을 입력해주세요.")


def get_chatgpt_comment(post_content: str) -> str:
    """
    OpenAI API를 사용하여 게시글에 대한 댓글 생성

    Args:
        post_content: 게시글 본문 내용

    Returns:
        str: ChatGPT가 생성한 댓글
    """
    try:
        print("  OpenAI API로 댓글 요청 중...")

        # OpenAI API 키 가져오기
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("  ⚠ .env 파일에 OPENAI_API_KEY가 설정되지 않았습니다.")
            return ""

        # OpenAI 클라이언트 생성
        client = OpenAI(api_key=api_key)

        # 프롬프트 작성
        prompt = f"아래의 글을 읽고 구어체로 간단하게 한줄 댓글을 작성해줘. 존댓말을 사용하고 답변으로는 딱 한줄 댓글만 작성해줘. 글 내용: {post_content[:1000]}"  # 내용이 너무 길면 처음 1000자만

        # ChatGPT API 호출
        response = client.responses.create(
            model="gpt-5-nano",
            reasoning={"effort": "low"},
            instructions="당신은 친근한 카페 회원입니다. 간단하고 따뜻한 한줄 댓글을 작성해주세요.",
            input=prompt
        )

        # 응답 추출
        comment = response.output_text
        print(f"  ✓ ChatGPT 응답 수신 완료 (길이: {len(comment)}자)")
        return comment

    except Exception as e:
        print(f"  ChatGPT 댓글 생성 중 오류 발생: {e}")
        return ""


async def post_comment(page: Page, post_url: str, comment_text: str) -> bool:
    """
    게시글에 댓글 작성 및 등록

    Args:
        page: Playwright Page 객체
        post_url: 게시글 URL
        comment_text: 작성할 댓글 내용

    Returns:
        bool: 댓글 등록 성공 여부
    """
    try:
        print(f"\n댓글 등록 시도 중...")
        print(f"댓글 내용: {comment_text}")

        # 게시글 페이지로 이동 (이미 해당 페이지에 있을 수 있음)
        current_url = page.url
        if current_url != post_url:
            await page.goto(post_url)
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(2000)

        # iframe 존재 여부 확인
        iframe_exists = await page.locator("iframe#cafe_main").count() > 0

        if iframe_exists:
            print("  iframe 모드로 댓글 작성 중...")
            cafe_iframe = page.frame_locator("iframe#cafe_main")

            # 댓글 입력창 찾기 (여러 선택자 시도)
            comment_selectors = [
                "textarea[name='memo']",
                "textarea.textarea",
                "textarea#memo",
                ".comment_inbox textarea",
                "[class*='comment'] textarea",
            ]

            comment_input = None
            for selector in comment_selectors:
                try:
                    comment_input = cafe_iframe.locator(selector).first
                    if await comment_input.count() > 0:
                        print(f"  댓글 입력창 발견 (선택자: {selector})")
                        break
                except:
                    continue

            if not comment_input or await comment_input.count() == 0:
                print("  ⚠ 댓글 입력창을 찾을 수 없습니다.")
                return False

            # 댓글 입력
            await comment_input.click()
            await page.wait_for_timeout(500)
            await comment_input.fill(comment_text)
            await page.wait_for_timeout(1000)

            # 댓글 등록 버튼 찾기
            submit_selectors = [
                "button:has-text('등록')",
                "a:has-text('등록')",
                "input[type='button'][value='등록']",
                "input[type='submit'][value='등록']",
                ".btn_register",
                "#btn_register",
            ]

            submit_button = None
            for selector in submit_selectors:
                try:
                    submit_button = cafe_iframe.locator(selector).first
                    if await submit_button.count() > 0:
                        print(f"  등록 버튼 발견 (선택자: {selector})")
                        break
                except:
                    continue

            if not submit_button or await submit_button.count() == 0:
                print("  ⚠ 등록 버튼을 찾을 수 없습니다.")
                return False

            # 등록 버튼 클릭
            await submit_button.click()
            await page.wait_for_timeout(2000)

        else:
            print("  일반 페이지 모드로 댓글 작성 중...")

            # 댓글 입력창 찾기
            comment_selectors = [
                "textarea[name='memo']",
                "textarea.textarea",
                "textarea#memo",
                ".comment_inbox textarea",
                "[class*='comment'] textarea",
                "[class*='Comment'] textarea",
            ]

            comment_input = None
            for selector in comment_selectors:
                try:
                    if await page.locator(selector).count() > 0:
                        comment_input = page.locator(selector).first
                        print(f"  댓글 입력창 발견 (선택자: {selector})")
                        break
                except:
                    continue

            if not comment_input:
                print("  ⚠ 댓글 입력창을 찾을 수 없습니다.")
                return False

            # 댓글 입력
            await comment_input.click()
            await page.wait_for_timeout(500)
            await comment_input.fill(comment_text)
            await page.wait_for_timeout(1000)

            # 댓글 등록 버튼 찾기
            submit_selectors = [
                "button:has-text('등록')",
                "a:has-text('등록')",
                "input[type='button'][value='등록']",
                "input[type='submit'][value='등록']",
                ".btn_register",
                "#btn_register",
            ]

            submit_button = None
            for selector in submit_selectors:
                try:
                    if await page.locator(selector).count() > 0:
                        submit_button = page.locator(selector).first
                        print(f"  등록 버튼 발견 (선택자: {selector})")
                        break
                except:
                    continue

            if not submit_button:
                print("  ⚠ 등록 버튼을 찾을 수 없습니다.")
                return False

            # 등록 버튼 클릭
            await submit_button.click()
            await page.wait_for_timeout(2000)

        print("  ✓ 댓글 등록 완료")
        return True

    except Exception as e:
        print(f"  댓글 등록 중 오류 발생: {e}")
        return False


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
            headless=False,  # 브라우저 창 표시 안함 (백그라운드 실행)
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

            print(f"\n2일 전 작성된 게시글: {len(two_days_posts)}개")

            if len(two_days_posts) < 5:
                print(f"  (5개 미만이지만 {len(two_days_posts)}개 게시글 모두 처리합니다)")

            # 각 게시글 방문하고 본문 수집
            post_contents = []
            for post in two_days_posts:
                post_data = await visit_post(page, post["url"], post["title"])
                post_contents.append(post_data)
                await page.wait_for_timeout(1000)  # 잠시 대기

            # ChatGPT로 댓글 생성
            print(f"\n\n{'='*60}")
            print(f"[{board['name']}] ChatGPT 댓글 생성 중")
            print(f"{'='*60}\n")

            for idx, post_data in enumerate(post_contents, 1):
                print(f"\n--- 게시글 {idx} ---")
                print(f"제목: {post_data['title']}")
                print(f"URL: {post_data['url']}")
                print(f"본문 길이: {len(post_data['content'])}자")

                # ChatGPT로 댓글 생성
                if post_data['content']:
                    comment = get_chatgpt_comment(post_data['content'])
                    post_data['comment'] = comment

                    if comment:
                        # 사용자 확인 받기
                        user_approved = get_user_confirmation(comment)

                        if user_approved:
                            # 댓글 등록
                            print(f"\n[댓글 등록 시작]")
                            success = await post_comment(page, post_data['url'], comment)

                            if success:
                                print("  ✓ 댓글이 성공적으로 등록되었습니다!")
                            else:
                                print("  ✗ 댓글 등록에 실패했습니다.")

                            # 다음 게시글로 이동하기 전 대기
                            await page.wait_for_timeout(2000)
                        else:
                            # 사용자가 N을 선택한 경우
                            print("다음 게시글로 이동합니다...")
                    else:
                        print("\n[생성된 댓글]")
                        print("(댓글 생성 실패 - 등록 건너뜀)")
                else:
                    print("\n[생성된 댓글]")
                    print("(본문이 없어 댓글을 생성할 수 없습니다)")
                    post_data['comment'] = ""

                print(f"\n{'='*60}")

        print("\n" + "="*60)
        print("모든 작업 완료! 브라우저를 수동으로 닫아주세요.")
        print("="*60)

        # 브라우저 자동 종료 비활성화 (사용자가 직접 닫음)
        # await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
