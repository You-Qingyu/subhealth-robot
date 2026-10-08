#!/usr/bin/env bash
set -eo pipefail

source /opt/ros/jazzy/setup.bash
source /opt/ros/overlay/setup.bash

pids=()

spawn() {
    "$@" &
    pids+=($!)
}

cleanup() {
    kill "${pids[@]}" 2>/dev/null || true
    wait "${pids[@]}" 2>/dev/null || true
}

trap cleanup EXIT INT TERM

spawn ros2 run mock_exec_layer mock_exec_layer_node
spawn ros2 run physio_mock_publisher physio_mock_publisher_node
spawn ros2 run gateway gateway

wait -n "${pids[@]}"
status=$?
exit "$status"
