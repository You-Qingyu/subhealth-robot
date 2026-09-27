# ROS Subhealth — one entry point for every routine task.
#
# Canonical workflow: WebUI, server/endpoint runtime, and ROS image selection.
#
#   make help

SHELL := /bin/bash

COMPOSE   := docker compose -f docker/dev/compose.yaml
DEV        := $(COMPOSE) run --rm dev
# Make decides at startup whether it is already inside Docker.
IN_CONTAINER := $(if $(wildcard /.dockerenv),1,0)

# Load local, uncommitted settings when present. The file uses Make-compatible
# `KEY=VALUE` lines, which also keeps it usable by Docker Compose.
-include .env

# Overridable settings.
GATEWAY_HTTP_PORT ?= 5000
ROS_BUILD_ROOT ?= $(if $(filter 1,$(IN_CONTAINER)),/ws/$(ROS_DISTRO),$(CURDIR))
ENDPOINT_ARGS ?=
ROS_DISTRO ?= jazzy
ROS_DOMAIN_ID ?= 1
RMW_IMPLEMENTATION ?= rmw_cyclonedds_cpp
TONYPI_ROOT ?= /home/pi/TonyPi
ROS_TASK_CLIENT_CONFIG ?= ros2_ws/config/devices.yaml

.DEFAULT_GOAL := help

.PHONY: help humble jazzy build \
        fmt lint check webui webui-dev run server endpoint clean

## help: list available targets
help:
	@echo "ROS Subhealth targets:"
	@echo
	@echo "  make humble          Build the Ubuntu 22.04 + ROS Humble image and enter it"
	@echo "  make jazzy           Build the Ubuntu 24.04 + ROS Jazzy image and enter it"
	@echo "  make build           Build the ROS workspace packages in the container"
	@echo "  make fmt             Format the Rust workspace"
	@echo "  make lint            Check formatting and run clippy"
	@echo "  make check           Rust lint + build"
	@echo "  make webui           Install deps and build the WebUI"
	@echo "  make webui-dev       Run the WebUI dev server"
	@echo "  make run server      Run the control-plane server"
	@echo "  make run endpoint DEVICE_TYPE=<device-type>"
	@echo "  make clean           Remove build artifacts"
	@echo
	@echo "  endpoint requires DEVICE_TYPE; server and endpoint are mutually exclusive"

## humble: build the Humble image and enter an interactive development container
humble:
	ROS_DISTRO=humble UBUNTU_VERSION=22.04 $(COMPOSE) build --build-arg ROS_DISTRO=humble --build-arg UBUNTU_VERSION=22.04
	ROS_DISTRO=humble UBUNTU_VERSION=22.04 $(COMPOSE) run --rm dev bash

## jazzy: build the Jazzy image and enter an interactive development container
jazzy:
	ROS_DISTRO=jazzy UBUNTU_VERSION=24.04 $(COMPOSE) build --build-arg ROS_DISTRO=jazzy --build-arg UBUNTU_VERSION=24.04
	ROS_DISTRO=jazzy UBUNTU_VERSION=24.04 $(COMPOSE) run --rm dev bash

## build: build ROS workspace packages in the container, or the Cargo workspace on the host
build:
ifeq ($(IN_CONTAINER),1)
	# colcon-cargo regenerates this ignored file from the selected ROS distro;
	# remove the previous distro's patches before building in the shared checkout.
	rm -f .cargo/config.toml
	source /opt/ros/$(ROS_DISTRO)/setup.bash && colcon --log-base $(ROS_BUILD_ROOT)/log build --merge-install --base-paths ros2_ws/src --build-base $(ROS_BUILD_ROOT)/build/merged-symlink --install-base $(ROS_BUILD_ROOT)/install --symlink-install
else
	cargo build --workspace
endif

## fmt: format the Rust workspace
fmt:
	cargo fmt --all

## lint: formatting + clippy
lint:
	cargo fmt --all --check
	@lint_dir="$$(mktemp -d "$${TMPDIR:-/tmp}/ros-subhealth-lint.XXXXXX")"; \
		trap 'rm -rf -- "$$lint_dir"' EXIT; \
		cd "$$lint_dir" && cargo clippy --manifest-path "$(CURDIR)/Cargo.toml" --all-targets -- -D warnings

## check: lint + build
check: lint build

## webui: install deps and build the WebUI
webui:
ifeq ($(IN_CONTAINER),1)
	cd webui && pnpm install --frozen-lockfile && pnpm build
else
	$(DEV) make webui
endif

## webui-dev: run the WebUI dev server
webui-dev:
ifeq ($(IN_CONTAINER),1)
	cd webui && pnpm install --frozen-lockfile && pnpm dev
else
	$(DEV) make webui-dev
endif

## run: dispatch to exactly one runtime mode
run:
	@case " $(MAKECMDGOALS) " in \
	  *" server "*) if [ "$(IN_CONTAINER)" = "1" ]; then \
	    test -f "$(ROS_BUILD_ROOT)/install/setup.bash" || { echo "ROS install setup not found at $(ROS_BUILD_ROOT)/install/setup.bash; run 'make build' inside the ROS container first" >&2; exit 2; }; \
	    source /opt/ros/$(ROS_DISTRO)/setup.bash && \
	    source "$(ROS_BUILD_ROOT)/install/setup.bash" && \
    GATEWAY_HTTP_PORT="$(GATEWAY_HTTP_PORT)" ROS_TASK_CLIENT_CONFIG="$(ROS_TASK_CLIENT_CONFIG)" cargo run -p gateway; \
  else $(DEV) make run server GATEWAY_HTTP_PORT="$(GATEWAY_HTTP_PORT)" ROS_TASK_CLIENT_CONFIG="$(ROS_TASK_CLIENT_CONFIG)"; fi ;; \
	  *" endpoint "*) \
	    case "$(DEVICE_TYPE)" in \
      mock-exec) ros_package=mock_exec_layer; ros_executable=mock_exec_layer_node ;; \
      tonypi) ros_package=tonypi_exec_layer; ros_executable=tonypi_exec_layer_node ;; \
	      mock-sensor) ros_package=physio_mock_publisher; ros_executable=physio_mock_publisher_node ;; \
      "") echo "usage: make run endpoint DEVICE_TYPE=<device-type>" >&2; echo "supported DEVICE_TYPE values: mock-exec, mock-sensor, tonypi" >&2; exit 2 ;; \
      *) echo "unsupported DEVICE_TYPE=$(DEVICE_TYPE); supported DEVICE_TYPE values: mock-exec, mock-sensor, tonypi" >&2; exit 2 ;; \
	    esac; \
	    test -f "$(ROS_BUILD_ROOT)/install/setup.bash" || { echo "ROS install setup not found at $(ROS_BUILD_ROOT)/install/setup.bash; run 'make build' inside the ROS container first" >&2; exit 2; }; \
	    source /opt/ros/$(ROS_DISTRO)/setup.bash && \
	    source "$(ROS_BUILD_ROOT)/install/setup.bash" && \
    ROS_DOMAIN_ID="$(ROS_DOMAIN_ID)" RMW_IMPLEMENTATION="$(RMW_IMPLEMENTATION)" TONYPI_ROOT="$(TONYPI_ROOT)" ros2 run "$$ros_package" "$$ros_executable" $(if $(strip $(ENDPOINT_ARGS)),--ros-args $(ENDPOINT_ARGS),) ;; \
	  *) echo "usage: make run server | make run endpoint DEVICE_TYPE=<device-type>" >&2; exit 2 ;; \
	esac

server endpoint:
	@:

## clean: remove build artifacts
clean:
	cargo clean
	rm -rf webui/dist dist
