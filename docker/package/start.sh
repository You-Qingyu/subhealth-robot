#!/usr/bin/env bash
set -euo pipefail

package_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
archive="$package_dir/rtos-subhealth-images.tar.gz"

read_env_value() {
    local file="$1" key="$2" value
    [[ -f "$file" ]] || return 0
    value="$(sed -n "s/^[[:space:]]*${key}[[:space:]]*=[[:space:]]*//p" "$file" | tail -n 1)"
    value="${value//$'\r'/}"
    value="${value//\"/}"
    value="${value//\'/}"
    printf '%s' "$value"
}

web_port="${WEB_PORT:-$(read_env_value "$package_dir/.env" WEB_PORT)}"
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

agent_key="${OPENAI_API_KEY:-$(read_env_value "$package_dir/.env" OPENAI_API_KEY)}"
if [[ -n "$agent_key" ]]; then
    docker compose --profile agent -f compose.yaml up -d agent
    printf '智能体服务已启动，WebUI 的 Agent 页面可直接对话。\n'
else
    docker compose --profile agent -f compose.yaml stop agent >/dev/null
    printf '未配置 OPENAI_API_KEY，智能体服务未启动；WebUI 的 Agent 页面暂不可用。\n'
fi

printf '评审演示已启动： http://127.0.0.1:%s\n' "$web_port"
