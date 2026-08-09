@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo   MarketSignal - запуск бота
echo ============================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [1/2] Создаю виртуальное окружение...
    python -m venv .venv
)

echo [2/2] Проверяю зависимости...
.venv\Scripts\python.exe -m pip install --quiet --upgrade pip
.venv\Scripts\python.exe -m pip install --quiet -e "."

if not exist "config\.env" (
    copy config\.env.example config\.env >nul
    echo.
    echo [!] Создан config\.env - заполните BOT_TOKEN и ADMIN_IDS!
    echo.
    pause
    exit /b
)

echo.
echo Запускаю бота...
.venv\Scripts\python.exe main.py
pause
