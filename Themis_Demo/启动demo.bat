@echo off
chcp 936 >/dev/null
cd /d "%~dp0"
echo ============================================
echo   Themis 现场体验 demo 启动中...
echo   浏览器将自动打开 http://127.0.0.1:7860
echo   关闭本窗口即可停止服务
echo ============================================
python app.py
pause
