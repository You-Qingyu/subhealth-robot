@echo off
setlocal
cd /d "%~dp0"

docker info >nul 2>&1
if errorlevel 1 (
  echo Docker 未运行。请安装并启动 Docker Desktop，并启用 Linux 容器。
  exit /b 1
)

docker image inspect rtos-subhealth-demo:jazzy >nul 2>&1
if errorlevel 1 goto load_images
docker image inspect rtos-subhealth-web:jazzy >nul 2>&1
if errorlevel 1 goto load_images
goto start_demo

:load_images
if not exist "%~dp0rtos-subhealth-images.tar.gz" (
  echo 找不到镜像归档 rtos-subhealth-images.tar.gz。
  exit /b 1
)
docker load --input "%~dp0rtos-subhealth-images.tar.gz"
if errorlevel 1 exit /b 1

:start_demo
docker compose -f compose.yaml up -d
if errorlevel 1 exit /b 1
echo 评审演示已启动：http://localhost:8080
endlocal
