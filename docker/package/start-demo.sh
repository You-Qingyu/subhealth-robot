#!/usr/bin/env bash
set -euo pipefail

package_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
archive="$package_dir/rtos-subhealth-images.tar.gz"

read_web_port() {
    local value
    [[ -f "$1" ]] || return 0
    value="$(sed -n 's/^[[:space:]]*WEB_PORT[[:space:]]*=[[:space:]]*//p' "$1" | tail -n 1)"
    value="${value//$'\r'/}"
    value="${value//\"/}"
    value="${value//\'/}"
    printf '%s' "$value"
}

web_port="${WEB_PORT:-$(read_web_port "$package_dir/.env")}"
web_port="${web_port:-8080}"

docker info >/dev/null || {
    printf 'Docker 未运行；请先安装并启动 Docker Desktop 或 Docker Engine。\n' >&2
    exit 1
}

if ! docker image inspect rtos-subhealth-demo:jazzy >/dev/null 2>&1 \
    || ! docker image inspect rtos-subhealth-web:jazzy >/dev/null 2>&1; then
    if [[ ! -f "$archive" ]]; then
        printf '缺少 Docker 镜像和归档文件：%s\n' "$archive" >&2
        exit 1
    fi
    docker load --input "$archive"
fi

cd "$package_dir"
docker compose -f compose.yaml up -d
printf '评审演示已启动： http://127.0.0.1:%s\n' "$web_port"
