#!/usr/bin/env bash
set -eo pipefail

source /opt/ros/jazzy/setup.bash
source /opt/ros/overlay/setup.bash

ros2 run mock_exec_layer mock_exec_layer_node &
mock_pid=$!
ros2 run gateway gateway &
gateway_pid=$!

cleanup() {
    kill "$gateway_pid" "$mock_pid" 2>/dev/null || true
    wait "$gateway_pid" 2>/dev/null || true
    wait "$mock_pid" 2>/dev/null || true
}

trap cleanup EXIT INT TERM
wait -n "$gateway_pid" "$mock_pid"
status=$?
exit "$status"
