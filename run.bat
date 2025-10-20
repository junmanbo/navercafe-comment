@echo off
chcp 65001 > nul
echo ========================================
echo 네이버 카페 댓글 자동화 프로그램 실행
echo ========================================
echo.

REM 현재 bat 파일이 있는 디렉토리로 이동
cd /d "%~dp0"

echo 현재 디렉토리: %CD%
echo.

REM .venv 폴더 존재 여부 확인
if not exist ".venv\" (
    echo [오류] .venv 폴더를 찾을 수 없습니다.
    echo 먼저 가상환경을 생성해주세요: uv sync
    echo.
    pause
    exit /b 1
)

echo 가상환경 활성화 중...
call .venv\Scripts\activate.bat

if errorlevel 1 (
    echo [오류] 가상환경 활성화에 실패했습니다.
    echo.
    pause
    exit /b 1
)

echo 가상환경 활성화 완료!
echo.

echo main.py 실행 중...
echo ========================================
echo.

python main.py

echo.
echo ========================================
echo 프로그램 실행 완료
echo ========================================
echo.

REM 가상환경 비활성화
deactivate

pause
