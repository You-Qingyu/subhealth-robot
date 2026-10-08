@echo off
setlocal
cd /d "%~dp0"

docker info >nul 2>&1
if errorlevel 1 goto docker_down

docker image inspect rtos-subhealth-demo:jazzy >nul 2>&1
if errorlevel 1 goto load_images
docker image inspect rtos-subhealth-web:jazzy >nul 2>&1
if errorlevel 1 goto load_images
goto start_demo

:load_images
if not exist "%~dp0rtos-subhealth-images.tar.gz" goto no_archive
echo 正在导入 Docker 镜像，请稍候...
docker load --input "%~dp0rtos-subhealth-images.tar.gz"
if errorlevel 1 goto fail
goto start_demo

:start_demo
docker compose -f compose.yaml up -d
if errorlevel 1 goto fail

set "AGENT_KEY=%OPENAI_API_KEY%"
if defined AGENT_KEY goto start_agent
if not exist ".env" goto stop_agent
for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env") do if /i "%%A"=="OPENAI_API_KEY" set "AGENT_KEY=%%~B"
if not defined AGENT_KEY goto stop_agent
goto start_agent

:stop_agent
docker compose --profile agent -f compose.yaml stop agent >nul 2>&1
goto web_port

:start_agent
echo 检测到 OPENAI_API_KEY，正在启动智能体服务...
docker compose --profile agent -f compose.yaml up -d agent
if errorlevel 1 goto fail

:web_port
set "PORT=8080"
if not defined WEB_PORT goto read_env_file
set "PORT=%WEB_PORT%"
goto port_ready

:read_env_file
if not exist ".env" goto port_ready
for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env") do if /i "%%A"=="WEB_PORT" set "PORT=%%~B"

:port_ready
echo 评审演示已启动： http://127.0.0.1:%PORT%
start "" "http://127.0.0.1:%PORT%"
endlocal
exit /b 0

:docker_down
echo Docker 未运行。请安装并启动 Docker Desktop，并启用 Linux 容器。
goto fail

:no_archive
echo 找不到镜像归档 rtos-subhealth-images.tar.gz。
goto fail

:fail
pause
endlocal
exit /b 1
