#!/usr/bin/env bash
set -eo pipefail

repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../../.." && pwd)
build_root=${ROS_BUILD_ROOT:-/ws/${ROS_DISTRO}}
log_file=/tmp/ros-task-client-mock.log
integration_timeout=${ROS_TASK_CLIENT_INTEGRATION_TIMEOUT:-180}
mock_pid=""
mock_pgid=""
cargo_target_dir=""
remove_cargo_target=0
cargo_work_dir=""

source "/opt/ros/${ROS_DISTRO}/setup.bash"
source "${build_root}/install/setup.bash"
set -u

action_is_present() {
  local actions
  if ! actions=$(timeout --signal=TERM --kill-after=1s 3s ros2 action list); then
    echo "failed to query ROS action graph" >&2
    return 2
  fi
  grep -Fxq '/mock_exec/execute_task' <<<"${actions}"
}

preflight_deadline=$((SECONDS + 2))
while ((SECONDS < preflight_deadline)); do
  set +e
  action_is_present
  graph_status=$?
  set -e
  case "${graph_status}" in
    0)
      echo "refusing to run with stale /mock_exec/execute_task action" >&2
      exit 1
      ;;
    1) sleep 0.1 ;;
    *) exit 1 ;;
  esac
done

: >"${log_file}"
mock_executable=$(ros2 pkg prefix mock_exec_layer)/lib/mock_exec_layer/mock_exec_layer_node
if [[ ! -x "${mock_executable}" ]]; then
  echo "mock executable is not runnable: ${mock_executable}" >&2
  exit 1
fi

setsid "${mock_executable}" \
  --ros-args -p step_delay_s:=0.05 \
  >"${log_file}" 2>&1 &
mock_pid=$!
mock_pgid=$(ps -o pgid= -p "${mock_pid}" | tr -d '[:space:]')
caller_pgid=$(ps -o pgid= -p "$$" | tr -d '[:space:]')
if [[ -z "${mock_pgid}" || "${mock_pgid}" != "${mock_pid}" || "${mock_pgid}" == "${caller_pgid}" ]]; then
  kill "${mock_pid}" 2>/dev/null || true
  wait "${mock_pid}" 2>/dev/null || true
  echo "mock did not start in a dedicated process group" >&2
  exit 1
fi

stop_mock() {
  local original_status=$?
  local cleanup_status=0
  trap - EXIT INT TERM
  set +e

  if [[ -n "${mock_pgid:-}" && "${mock_pgid}" != "${caller_pgid:-}" ]]; then
    kill -TERM -- "-${mock_pgid}" 2>/dev/null
    local deadline=$((SECONDS + 5))
    while kill -0 -- "-${mock_pgid}" 2>/dev/null && ((SECONDS < deadline)); do
      sleep 0.1
    done
    if kill -0 -- "-${mock_pgid}" 2>/dev/null; then
      kill -KILL -- "-${mock_pgid}" 2>/dev/null
    fi

    wait "${mock_pid:-}" 2>/dev/null
    deadline=$((SECONDS + 2))
    while kill -0 -- "-${mock_pgid}" 2>/dev/null && ((SECONDS < deadline)); do
      sleep 0.1
    done
    if kill -0 -- "-${mock_pgid}" 2>/dev/null; then
      echo "mock process group ${mock_pgid} survived cleanup" >&2
      cleanup_status=1
    fi

  elif [[ -n "${mock_pgid:-}" ]]; then
    echo "refusing to signal caller process group ${mock_pgid}" >&2
    cleanup_status=1
  fi

  local graph_deadline=$((SECONDS + 10))
  while ((SECONDS < graph_deadline)); do
    action_is_present
    local graph_status=$?
    if ((graph_status == 1)); then
      break
    fi
    if ((graph_status > 1)); then
      cleanup_status=1
      break
    fi
    sleep 0.1
  done
  action_is_present
  graph_status=$?
  if ((graph_status == 0)); then
    echo "/mock_exec/execute_task persisted after mock cleanup" >&2
    cleanup_status=1
  elif ((graph_status > 1)); then
    cleanup_status=1
  fi

  if ((remove_cargo_target)) && [[ -n "${cargo_target_dir}" ]]; then
    rm -rf -- "${cargo_target_dir}" || cleanup_status=1
  fi
  if [[ -n "${cargo_work_dir}" ]]; then
    rm -rf -- "${cargo_work_dir}" || cleanup_status=1
  fi

  if ((original_status != 0)); then
    if ((cleanup_status != 0)); then
      echo "cleanup also failed after test status ${original_status}" >&2
    fi
    exit "${original_status}"
  fi
  exit "${cleanup_status}"
}
trap stop_mock EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

deadline=$((SECONDS + 10))
while true; do
  set +e
  action_is_present
  graph_status=$?
  set -e
  if ((graph_status == 0)); then
    break
  fi
  if ((graph_status > 1)); then
    exit 1
  fi
  if ! kill -0 -- "-${mock_pgid}" 2>/dev/null; then
    wait "${mock_pid}" || true
    cat "${log_file}" >&2
    exit 1
  fi
  if ((SECONDS >= deadline)); then
    cat "${log_file}" >&2
    exit 1
  fi
  sleep 0.1
done

if [[ -z "${CARGO_TARGET_DIR:-}" ]]; then
  cargo_target_dir=$(mktemp -d "${TMPDIR:-/tmp}/ros-task-client-integration.XXXXXX")
  remove_cargo_target=1
else
  cargo_target_dir=${CARGO_TARGET_DIR}
fi

cargo_work_dir=$(mktemp -d "${TMPDIR:-/tmp}/ros-task-client-cargo.XXXXXX")
cd "${cargo_work_dir}"
MOCK_EXECUTABLE="${mock_executable}" \
 CARGO_TARGET_DIR="${cargo_target_dir}" \
 timeout --signal=TERM --kill-after=10s "${integration_timeout}s" cargo test \
   --manifest-path "${repo_root}/ros2_ws/src/control_plane/ros_task_client/Cargo.toml" \
   --test mock_exec -- --ignored --test-threads=1
