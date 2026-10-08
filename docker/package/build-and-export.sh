#!/usr/bin/env bash
set -euo pipefail

package_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$package_dir/../.." && pwd)"
output="${1:-$package_dir/rtos-subhealth-images.tar.gz}"
output_dir="$(dirname -- "$output")"
mkdir -p "$output_dir"
temporary_output="$output.tmp.$$"
trap 'rm -f -- "$temporary_output"' EXIT

docker info >/dev/null

docker compose -f "$repo_root/docker/dev/compose.yaml" build dev
docker compose \
    -f "$package_dir/compose.yaml" \
    -f "$package_dir/compose.build.yaml" \
    build backend frontend

docker save rtos-subhealth-demo:jazzy rtos-subhealth-web:jazzy \
    | gzip -1 > "$temporary_output"
mv -- "$temporary_output" "$output"
trap - EXIT
printf 'Docker 镜像归档已生成：%s\n' "$output"
