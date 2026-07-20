@echo off
chcp 936 >nul
cd /d "%~dp0"
echo ============================================
echo   Themis 因果验证器 —— 网站启动中
echo   构建前端 + 启动服务,稍候自动打开浏览器
echo   地址: http://127.0.0.1:8000
echo   关闭本窗口即停止服务
echo ============================================
echo.
python "%~dp0scripts\launch_web.py"
echo.
echo 服务已停止。
pause
