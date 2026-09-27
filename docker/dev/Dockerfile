# Jazzy + Rust development image. Build once; source is bind-mounted at runtime.
#
#   docker build -t ros-dev:jazzy docker/dev
#   docker run --rm -it --network host -v "$PWD":/workspace ros-dev:jazzy
#
# All ROS/Rust/C++/Node tooling is provided by the container; nothing is
# required on the host when using the Dev Container.
ARG ROS_DISTRO=jazzy
FROM ros:${ROS_DISTRO}-ros-base
ARG UBUNTU_VERSION

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential cmake git curl pkg-config libclang-dev sudo \
      python3-pip python3-pytest python3-vcstool \
      ros-${ROS_DISTRO}-rmw-cyclonedds-cpp \
      ros-${ROS_DISTRO}-cv-bridge \
      ros-${ROS_DISTRO}-sensor-msgs \
      ros-${ROS_DISTRO}-rosidl-default-generators \
      ros-${ROS_DISTRO}-rosidl-default-runtime \
      ros-${ROS_DISTRO}-test-msgs \
      ros-${ROS_DISTRO}-example-interfaces \
  && rm -rf /var/lib/apt/lists/*

RUN case "${ROS_DISTRO}:${UBUNTU_VERSION}" in \
      humble:22.04) package_branch=jammy-humble ;; \
      jazzy:24.04) package_branch=noble-jazzy ;; \
      *) echo "unsupported ROS/Ubuntu pair: ${ROS_DISTRO}/${UBUNTU_VERSION}" >&2; exit 2 ;; \
    esac \
 && echo "deb [trusted=yes] https://raw.githubusercontent.com/ros2-rust/rosidl_rust/${package_branch}/ ./" \
      > /etc/apt/sources.list.d/ros2-rust-rosidl.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends ros-${ROS_DISTRO}-rosidl-generator-rs \
 && rm -rf /var/lib/apt/lists/*

# Reuse the base image's `ubuntu` user when present (Jazzy), and create the
# same non-root developer on base images that do not ship one (Humble). The Dev
# Container `updateRemoteUserUID` setting keeps its UID in sync with the host
# user when they differ.
RUN printf 'ubuntu ALL=(ALL) NOPASSWD:ALL\n' > /etc/sudoers.d/ubuntu \
 && if ! getent group ubuntu >/dev/null; then groupadd --gid 1000 ubuntu; fi \
 && if ! id -u ubuntu >/dev/null 2>&1; then useradd --uid 1000 --gid ubuntu --create-home --shell /bin/bash ubuntu; fi \
 && chmod 0440 /etc/sudoers.d/ubuntu

# Pinned Rust toolchain (matches rust-toolchain.toml), shared so both root and
# the dev user can use it.
ENV RUSTUP_HOME=/usr/local/rustup \
    CARGO_HOME=/usr/local/cargo \
    PATH=/usr/local/cargo/bin:${PATH}
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
      | sh -s -- -y --default-toolchain 1.85.0 --profile minimal \
                 --component rustfmt --component clippy --component rust-analyzer \
 && chmod -R a+w /usr/local/cargo /usr/local/rustup

# WebUI toolchain. Keep the Node major on the current LTS line and pin pnpm so
# frozen-lockfile installs behave the same across developer machines.
RUN curl -fsSL https://deb.nodesource.com/setup_24.x | bash - \
 && apt-get update \
 && apt-get install -y --no-install-recommends nodejs \
 && npm install --global pnpm@9.15.9 \
 && node --version \
 && pnpm --version \
 && rm -rf /var/lib/apt/lists/*

# The node build workspace is a named volume. Pre-create it owned by the dev
# user so a fresh volume inherits writable ownership; keep the shared Cargo home
# (registry cache mount lives at /usr/local/cargo/registry) writable too.
RUN mkdir -p /ws && chown ubuntu:ubuntu /ws \
 && chmod -R a+w /usr/local/cargo /usr/local/rustup

# colcon plugins that teach colcon to build Cargo packages (rclrs). Older
# Ubuntu images do not support pip's --break-system-packages option.
RUN pip install --no-cache-dir --break-system-packages colcon-cargo colcon-ros-cargo \
 || pip install --no-cache-dir colcon-cargo colcon-ros-cargo

ENV RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
ENV ROS_DOMAIN_ID=1

WORKDIR /workspace
CMD ["bash"]
