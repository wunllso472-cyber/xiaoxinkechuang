@echo off
REM 设置小信助手开机自启（当前用户）
set EXE=%~dp0XiaoxinAssistant.exe
if not exist "%EXE%" set EXE=%~dp0dist\XiaoxinAssistant\XiaoxinAssistant.exe
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v XiaoxinAssistant /t REG_SZ /d "\"%EXE%\"" /f
echo 已设置开机自启：%EXE%
pause
