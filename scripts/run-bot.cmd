@echo off
REM Запуск бота в фоне планировщиком заданий.
REM Рабочая папка = корень проекта, поэтому .env и data/ находятся правильно.
REM Весь вывод пишется в logs\bot.log, иначе при запуске без консоли он теряется.

cd /d "%~dp0.."
set PYTHONIOENCODING=utf-8
if not exist logs mkdir logs

REM Лог не должен расти бесконечно: при 5 МБ старый файл переименовывается.
if exist "logs\bot.log" for %%A in ("logs\bot.log") do if %%~zA GTR 5242880 move /y "logs\bot.log" "logs\bot.old.log" >nul

echo [%DATE% %TIME%] start >> "logs\bot.log"
".venv\Scripts\python.exe" -m cocktail bot >> "logs\bot.log" 2>&1
echo [%DATE% %TIME%] exit code %ERRORLEVEL% >> "logs\bot.log"
