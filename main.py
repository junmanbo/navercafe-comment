import asyncio
import os
import re

from dotenv import load_dotenv
from playwright.async_api import Page, async_playwright
from openai import OpenAI

# .env 파일 로드
load_dotenv()

# 타임아웃 상수 정의 (밀리초)
TIMEOUT_VERY_SHORT = 100
TIMEOUT_SHORT = 300
TIMEOUT_MEDIUM = 500
TIMEOUT_LONG = 1000
TIMEOUT_VERY_LONG = 2000
TIMEOUT_EXTRA_LONG = 3000
TIMEOUT_BUTTON_ACTIVATION = 5000


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
        await page.wait_for_timeout(TIMEOUT_VERY_LONG)  # 페이지 로딩 대기

        # 좌측 메뉴의 게시판 링크들 찾기
        # 네이버 카페의 좌측 메뉴 구조를 탐색
        boards = []

        # 좌측 메뉴의 게시판 링크 찾기
        menu_items = await page.locator("a.gm-tcol-c").all()

        for item in menu_items:
            try:
                name = await item.inner_text()
                href = await item.get_attribute("href")

                if name and href:
                    boards.append({
                        "name": name.strip(),
                        "url": href
                    })
            except Exception:
                continue

        return boards

    except Exception as e:
        print(f"게시판 목록 불러오기 중 오류 발생: {e}")
        return []


async def process_board_page_by_page(page: Page, board_url: str, board_name: str, target_date: str, max_pages: int, openai_client, comment_count: int, max_comment_count: int) -> tuple[int, bool]:
    """
    게시판 페이지를 순회하면서 한 게시글씩 처리

    Args:
        page: Playwright Page 객체
        board_url: 게시판 URL (기본 URL)
        board_name: 게시판 이름
        target_date: 찾을 날짜 (YYYY.MM.DD 형식, 또는 ":" for today)
        max_pages: 순회할 최대 페이지 수
        openai_client: OpenAI 클라이언트
        comment_count: 현재 댓글 카운트
        max_comment_count: 최대 댓글 수

    Returns:
        tuple[int, bool]: (업데이트된 comment_count, should_exit 플래그)
    """
    try:
        print(f"\n'{board_name}' 게시판 처리 시작...")

        # 게시판 페이지로 이동 (상대 경로를 절대 경로로 변환)
        if board_url.startswith("/"):
            base_board_url = f"https://cafe.naver.com{board_url}"
        else:
            base_board_url = board_url

        # 시간 형식 패턴 (HH:MM)
        time_pattern = re.compile(r'^\d{1,2}:\d{2}$')

        # 페이지별로 순회
        for page_num in range(1, max_pages + 1):
            if comment_count >= max_comment_count:
                print(f"\n목표 댓글 수({max_comment_count}개)에 도달하여 종료합니다.")
                return comment_count, True

            print(f"\n{'='*60}")
            print(f"[{board_name}] {page_num}페이지 처리 중")
            print(f"{'='*60}")

            # 페이지 URL 생성 - URL 파싱하여 올바르게 생성
            if page_num == 1:
                current_page_url = base_board_url
            else:
                # URL에 이미 파라미터가 있는지 확인
                if "?" in base_board_url:
                    # 기존 파라미터가 있으면 & 사용
                    current_page_url = f"{base_board_url}&page={page_num}"
                else:
                    # 파라미터가 없으면 ? 사용
                    current_page_url = f"{base_board_url}?page={page_num}"

            print(f"페이지 URL: {current_page_url}")

            # 게시판 페이지로 이동
            await page.goto(current_page_url)
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(TIMEOUT_EXTRA_LONG)

            # iframe 존재 여부 확인
            iframe_exists = await page.locator("iframe#cafe_main").count() > 0

            if iframe_exists:
                print("iframe 모드로 게시글 검색 중...")
                cafe_iframe = page.frame_locator("iframe#cafe_main")
                article_items = await cafe_iframe.locator("tr").all()
            else:
                print("일반 페이지 모드로 게시글 검색 중...")
                article_items = await page.locator("tr").all()

            print(f"발견된 전체 행 수: {len(article_items)}")

            # 이 페이지에서 처리한 게시글 수
            processed_posts_in_page = 0

            # 각 행을 순회하면서 오늘 날짜 게시글 찾기
            for item in article_items:
                if comment_count >= max_comment_count:
                    print(f"\n목표 댓글 수({max_comment_count}개)에 도달하여 종료합니다.")
                    return comment_count, True

                try:
                    # 날짜 찾기
                    date_text = ""
                    try:
                        date_elem = item.locator("td.td_date, td[class*='date'], .date, td:has-text('2025')")
                        date_text = await date_elem.inner_text(timeout=TIMEOUT_VERY_SHORT)
                    except Exception:
                        continue

                    # 날짜 텍스트가 비어있으면 스킵
                    if not date_text or date_text.strip() == "":
                        continue

                    # 오늘 게시글 (시간 형식) 또는 특정 날짜 게시글 필터링
                    is_match = False
                    if target_date == ":":
                        is_match = time_pattern.match(date_text.strip())
                    else:
                        is_match = target_date in date_text

                    if not is_match:
                        continue

                    # 제목과 URL 찾기
                    title = ""
                    post_url = ""
                    try:
                        title_elem = item.locator("a[href*='articles'], a[href*='Article']").first
                        title = await title_elem.inner_text(timeout=TIMEOUT_VERY_SHORT)
                        post_url = await title_elem.get_attribute("href", timeout=TIMEOUT_VERY_SHORT)
                    except Exception:
                        continue

                    if not title or not post_url:
                        continue

                    # 제목에 '공지'가 포함된 게시글은 제외
                    if '공지' in title:
                        print(f"  ⊗ [{date_text.strip()}] {title.strip()} (공지 게시글 제외)")
                        continue

                    # 상대 경로를 절대 경로로 변환
                    if post_url.startswith("/"):
                        post_url = f"https://cafe.naver.com{post_url}"

                    # 게시글 발견 - 바로 처리
                    processed_posts_in_page += 1
                    print(f"\n{'='*60}")
                    print(f"[{board_name}] {page_num}페이지 {processed_posts_in_page}번째 게시글 처리")
                    print(f"제목: {title.strip()}")
                    print(f"작성일: {date_text.strip()}")
                    print(f"현재 등록된 댓글 수: {comment_count}/{max_comment_count}")
                    print(f"{'='*60}")

                    # 게시글 방문하여 본문 가져오기
                    post_data = await visit_post(page, post_url, title.strip())
                    await page.wait_for_timeout(TIMEOUT_LONG)

                    # ChatGPT로 댓글 생성
                    if post_data['content']:
                        comment = get_chatgpt_comment(post_data['content'], openai_client)

                        if comment:
                            # 사용자 확인 받기
                            user_approved, comment = get_user_confirmation(comment)

                            if user_approved:
                                # 댓글 등록
                                print("\n[댓글 등록 시작]")
                                success = await post_comment(page, post_data['url'], comment)

                                if success:
                                    comment_count += 1
                                    print(f"  ✓ 댓글이 성공적으로 등록되었습니다! (총 {comment_count}개 등록)")

                                    # 60개 도달 시 종료
                                    if comment_count >= max_comment_count:
                                        print("\n" + "=" * 60)
                                        print(f"  목표 댓글 수({max_comment_count}개)에 도달했습니다!")
                                        print(f"  총 {comment_count}개의 댓글을 등록했습니다.")
                                        print("=" * 60)
                                        input("\n프로그램을 종료하려면 Enter 키를 눌러주세요...")
                                        return comment_count, True
                                else:
                                    print("  ✗ 댓글 등록에 실패했습니다.")

                                # 다음 게시글로 이동하기 전 대기
                                await page.wait_for_timeout(TIMEOUT_VERY_LONG)
                            else:
                                print("다음 게시글로 이동합니다...")
                        else:
                            print("(댓글 생성 실패 - 등록 건너뜀)")
                    else:
                        print("(본문이 없어 댓글을 생성할 수 없습니다)")

                    # 다시 게시판 페이지로 돌아가기
                    print(f"\n게시판 페이지로 돌아갑니다: {current_page_url}")
                    await page.goto(current_page_url)
                    await page.wait_for_load_state("networkidle")
                    await page.wait_for_timeout(TIMEOUT_EXTRA_LONG)

                    # iframe 다시 확인 (페이지가 바뀌었으므로)
                    iframe_exists = await page.locator("iframe#cafe_main").count() > 0
                    if iframe_exists:
                        cafe_iframe = page.frame_locator("iframe#cafe_main")
                        article_items = await cafe_iframe.locator("tr").all()
                    else:
                        article_items = await page.locator("tr").all()

                except Exception as e:
                    print(f"게시글 처리 중 오류: {e}")
                    continue

            # 해당 페이지에 오늘 날짜 게시글이 없으면 더 이상 다음 페이지 확인 안함
            if target_date == ":" and processed_posts_in_page == 0:
                print(f"\n{page_num}페이지에 오늘 작성된 게시글이 없어 페이지 순회를 중단합니다.")
                break

            print(f"\n{page_num}페이지에서 {processed_posts_in_page}개의 게시글을 처리했습니다.")

        return comment_count, False

    except Exception as e:
        print(f"'{board_name}' 게시판 처리 중 오류 발생: {e}")
        return comment_count, False


def get_user_confirmation(comment_text: str):
    """
    사용자에게 댓글 등록 확인 받기

    Args:
        comment_text: 등록할 댓글 내용

    Returns:
        bool: 등록 승인 여부 (Y: True, N: False)
    """
    print("\n" + "=" * 60)
    print("[생성된 댓글 내용]")
    print(f"\"{comment_text}\"")
    print("=" * 60)

    while True:
        response = input("\n정말 이 댓글로 등록하시겠습니까? [Y/N] \n댓글 수정을 원하면 [FIX]를 입력해 주세요.: ").strip().upper()

        if response == 'Y':
            print("✓ 댓글 등록을 진행합니다.")
            return True, comment_text
        elif response == 'N':
            print("✗ 댓글 등록을 건너뜁니다. 다음 게시글로 이동합니다.")
            return False, comment_text
        elif response == 'FIX':
            comment_text = input("댓글 수정을 진행합니다. (수정된 댓글로 바로 등록됩니다.)\n댓글을 입력해 주세요.: ")
            return True, comment_text
        else:
            print("⚠ 잘못된 입력입니다. Y 또는 N을 입력해주세요.")


async def find_element_by_selectors(locator_context, selectors: list[str], element_name: str) -> tuple:
    """
    여러 선택자를 시도하여 요소 찾기

    Args:
        locator_context: page 또는 frame_locator 객체
        selectors: 시도할 선택자 리스트
        element_name: 요소 이름 (로깅용)

    Returns:
        tuple: (element, selector) 또는 (None, None)
    """
    for selector in selectors:
        try:
            element = locator_context.locator(selector).first
            if await element.count() > 0:
                print(f"  {element_name} 발견 (선택자: {selector})")
                return element, selector
        except Exception:
            continue

    print(f"  ⚠ {element_name}을(를) 찾을 수 없습니다.")
    return None, None


async def process_comment_input(comment_input, page, comment_text: str) -> bool:
    """
    댓글 입력 처리 (공통 로직)

    Args:
        comment_input: 댓글 입력창 요소
        page: Page 객체
        comment_text: 입력할 댓글 내용

    Returns:
        bool: 입력 성공 여부
    """
    try:
        # 댓글 입력창으로 스크롤
        await comment_input.scroll_into_view_if_needed()
        await page.wait_for_timeout(TIMEOUT_MEDIUM)

        # 댓글 입력
        await comment_input.click()
        await page.wait_for_timeout(TIMEOUT_MEDIUM)

        # 기존 내용 지우기
        await comment_input.fill("")
        await page.wait_for_timeout(TIMEOUT_SHORT)

        # 댓글 입력
        await comment_input.fill(comment_text)
        await page.wait_for_timeout(TIMEOUT_LONG)

        # 입력이 제대로 되었는지 확인
        input_value = await comment_input.input_value()
        print(f"  입력된 댓글 확인: {input_value[:50]}...")
        return True
    except Exception as e:
        print(f"  댓글 입력 중 오류: {e}")
        return False


async def click_submit_button(submit_button, locator_context, page) -> bool:
    """
    등록 버튼 클릭 처리 (공통 로직)

    Args:
        submit_button: 등록 버튼 요소
        locator_context: page 또는 frame_locator 객체
        page: Page 객체

    Returns:
        bool: 클릭 성공 여부
    """
    try:
        # 등록 버튼으로 스크롤
        await submit_button.scroll_into_view_if_needed()
        await page.wait_for_timeout(TIMEOUT_SHORT)

        # 등록 버튼이 활성화될 때까지 대기
        try:
            await locator_context.locator("a.btn_register.is_active").wait_for(state="visible", timeout=TIMEOUT_BUTTON_ACTIVATION)
            print("  등록 버튼 활성화 확인")
        except Exception as e:
            print(f"  등록 버튼 활성화 대기 중 경고: {e}")

        # 등록 버튼 클릭 (force 옵션으로 강제 클릭)
        print("  등록 버튼 클릭 중...")
        try:
            await submit_button.click(force=True)
            print("  클릭 성공 (force=True)")
        except Exception as e:
            print(f"  일반 클릭 실패, JavaScript로 클릭 시도: {e}")
            # JavaScript로 직접 클릭
            await submit_button.evaluate("element => element.click()")

        await page.wait_for_timeout(TIMEOUT_EXTRA_LONG)
        return True
    except Exception as e:
        print(f"  버튼 클릭 중 오류: {e}")
        return False


def get_chatgpt_comment(post_content: str, client: OpenAI = None) -> str:
    """
    OpenAI API를 사용하여 게시글에 대한 댓글 생성

    Args:
        post_content: 게시글 본문 내용
        client: OpenAI 클라이언트 (선택적, 없으면 새로 생성)

    Returns:
        str: ChatGPT가 생성한 댓글
    """
    try:
        print("  OpenAI API로 댓글 요청 중...")

        # OpenAI 클라이언트가 없으면 생성
        if client is None:
            # OpenAI API 키 가져오기
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                print("  ⚠ .env 파일에 OPENAI_API_KEY가 설정되지 않았습니다.")
                return ""
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

        # 특수기호 제거 (한글, 영문, 숫자, 공백만 남기기)
        comment = re.sub(r'[^가-힣a-zA-Z0-9\s]', '', comment)

        # 양쪽 공백 제거
        comment = comment.strip()

        # 끝에 '! :)' 추가
        if comment:
            comment = comment + "! :)"

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
        print("\n댓글 등록 시도 중...")
        print(f"댓글 내용: {comment_text}")

        # 게시글 페이지로 이동 (이미 해당 페이지에 있을 수 있음)
        current_url = page.url
        if current_url != post_url:
            await page.goto(post_url)
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(TIMEOUT_VERY_LONG)

        # iframe 존재 여부 확인
        iframe_exists = await page.locator("iframe#cafe_main").count() > 0

        # 댓글 입력창 선택자
        comment_selectors = [
            "textarea[name='memo']",
            "textarea.textarea",
            "textarea#memo",
            ".comment_inbox textarea",
            "[class*='comment'] textarea",
            "[class*='Comment'] textarea",
        ]

        # 등록 버튼 선택자
        submit_selectors = [
            "a.btn_register.is_active",
            "a.btn_register",
            ".btn_register.is_active",
            ".btn_register",
            "a[role='button'].btn_register",
            "button:has-text('등록')",
            "a:has-text('등록')",
            "input[type='button'][value='등록']",
            "input[type='submit'][value='등록']",
            "#btn_register",
        ]

        # iframe 모드 또는 일반 페이지 모드 설정
        if iframe_exists:
            print("  iframe 모드로 댓글 작성 중...")
            locator_context = page.frame_locator("iframe#cafe_main")
        else:
            print("  일반 페이지 모드로 댓글 작성 중...")
            locator_context = page

        # 댓글 입력창 찾기
        comment_input, _ = await find_element_by_selectors(locator_context, comment_selectors, "댓글 입력창")
        if not comment_input:
            return False

        # 댓글 입력 처리
        if not await process_comment_input(comment_input, page, comment_text):
            return False

        # 등록 버튼 찾기
        submit_button, _ = await find_element_by_selectors(locator_context, submit_selectors, "등록 버튼")
        if not submit_button:
            return False

        # 등록 버튼 클릭 처리
        if not await click_submit_button(submit_button, locator_context, page):
            return False

        # 댓글 등록 확인 (입력창이 비워졌는지 확인)
        try:
            final_value = await comment_input.input_value()
            if final_value == "":
                print("  ✓ 댓글이 성공적으로 등록되었습니다 (입력창 비워짐 확인)")
            else:
                print(f"  ⚠ 댓글 등록 실패 가능성 (입력창에 텍스트 남아있음: {final_value[:30]}...)")
        except Exception:
            pass

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
        await page.wait_for_timeout(TIMEOUT_VERY_LONG)

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
                content = await content_elem.inner_text(timeout=TIMEOUT_EXTRA_LONG)
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
                        content = await content_elem.inner_text(timeout=TIMEOUT_LONG)
                        if content and content.strip():
                            print(f"  본문 추출 성공 (선택자: {selector})")
                            break
                    except Exception:
                        continue

            except Exception as e:
                print(f"  본문 추출 실패: {e}")

        # 본문이 비어있으면 전체 페이지 텍스트 가져오기 시도
        if not content or not content.strip():
            print("  기본 선택자로 본문을 찾을 수 없어 전체 페이지에서 추출 시도...")
            try:
                content = await page.inner_text("body")
            except Exception:
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
    openai_api_key = os.getenv("OPENAI_API_KEY")

    if not cafe_url:
        print(".env 파일에 CAFE_URL을 설정해주세요.")
        return

    # OpenAI 클라이언트 초기화 (한 번만 생성하여 재사용)
    openai_client = None
    if openai_api_key:
        openai_client = OpenAI(api_key=openai_api_key)
        print("OpenAI 클라이언트 초기화 완료")
    else:
        print("⚠ .env 파일에 OPENAI_API_KEY가 설정되지 않았습니다. 댓글 생성 기능을 사용할 수 없습니다.")

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
            await page.wait_for_timeout(TIMEOUT_MEDIUM)

            # 비밀번호 입력
            await page.fill('input[name="pw"]', naver_pw)
            await page.wait_for_timeout(TIMEOUT_MEDIUM)

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

        # 오늘 등록된 게시글 찾기 (시간 형식: HH:MM)
        print("\n오늘 등록된 게시글을 검색합니다 (시간 형식 HH:MM 체크)")

        check_boards = ["웨딩수다", "자랑", "진행", "맛집", "신부관리"]

        # 댓글 등록 카운터 초기화
        comment_count = 0
        max_comment_count = 60
        should_exit = False  # 종료 플래그

        # 각 게시판에서 오늘 등록된 게시글 확인 (시간 형식으로 표시된 글)
        for board in boards:
            if should_exit:
                break

            board_name = board['name']

            for check_board in check_boards:
                if should_exit:
                    break

                if check_board in board_name:
                    print(f"\n{'='*60}")
                    print(f"게시판: {board_name}")
                    print(f"{'='*60}")

                    # '웨딩수다' 게시판인 경우 5페이지까지 순회
                    max_pages = 5 if '웨딩수다' in board_name else 1

                    # 새로운 방식: 게시판 페이지를 순회하면서 한 게시글씩 처리
                    comment_count, should_exit = await process_board_page_by_page(
                        page=page,
                        board_url=board["url"],
                        board_name=board["name"],
                        target_date=":",
                        max_pages=max_pages,
                        openai_client=openai_client,
                        comment_count=comment_count,
                        max_comment_count=max_comment_count
                    )

                    if should_exit:
                        break

        # 종료 메시지 출력
        if not should_exit:
            print("\n" + "=" * 60)
            print("모든 게시판 확인 완료!")
            print(f"총 {comment_count}개의 댓글을 등록했습니다.")
            print("=" * 60)
            print("브라우저를 수동으로 닫아주세요.")
        else:
            print("\n프로그램을 종료합니다.")
            print("브라우저를 수동으로 닫아주세요.")

        # 브라우저 자동 종료 비활성화 (사용자가 직접 닫음)
        # await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
