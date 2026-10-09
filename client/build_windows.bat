@echo off
REM 打包 Windows 客户端（生成 dist\XiaoxinAssistant\XiaoxinAssistant.exe）
cd /d %~dp0
pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
pyinstaller --noconfirm --windowed --name XiaoxinAssistant ^
  --add-data "config.json;." ^
  --hidden-import xiaoxin_client --collect-submodules xiaoxin_client ^
  xiaoxin_client\main.py
copy /y config.json dist\XiaoxinAssistant\config.json
echo.
echo 打包完成：dist\XiaoxinAssistant\XiaoxinAssistant.exe
echo 部署前请修改 dist\XiaoxinAssistant\config.json 中的 server 地址；如需开机自启，运行 install_autostart_windows.bat
pause
