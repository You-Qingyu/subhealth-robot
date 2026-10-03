#!/usr/bin/env bash
set -euo pipefail

package_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
archive="$package_dir/rtos-subhealth-images.tar.gz"

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
printf '评审演示已启动： http://localhost:%s\n' "${WEB_PORT:-8080}"
