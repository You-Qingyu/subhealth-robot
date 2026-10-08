ARG ROS_BUILD_IMAGE=ros-dev:jazzy

FROM ${ROS_BUILD_IMAGE} AS build
WORKDIR /workspace
COPY . .

RUN bash -lc 'source /opt/ros/jazzy/setup.bash \
    && rm -f .cargo/config.toml \
    && colcon build --merge-install \
        --base-paths ros2_ws/src \
        --build-base /tmp/ros2-build \
        --install-base /opt/ros/overlay'

RUN cd /workspace/webui \
    && pnpm install --frozen-lockfile \
    && pnpm build

FROM ros:jazzy-ros-base AS backend

ARG ROS_APT_MIRROR=auto

ENV DEBIAN_FRONTEND=noninteractive \
    ROS_DISTRO=jazzy \
    ROS_DOMAIN_ID=1 \
    RMW_IMPLEMENTATION=rmw_cyclonedds_cpp \
    GATEWAY_HTTP_PORT=5000 \
    ROS_TASK_CLIENT_CONFIG=/opt/app/ros2_ws/config/devices.yaml \
    MAP_CONFIG=/opt/app/ros2_ws/config/maps/default.yaml \
    GATEWAY_URL=http://127.0.0.1:5000

RUN set -e; \
    sources=/etc/apt/sources.list.d/ros2.sources; \
    if [ "${ROS_APT_MIRROR}" = "auto" ]; then \
        printf '%s\n' \
            'URIs: https://mirrors.ustc.edu.cn/ros2/ubuntu' \
            'URIs: https://mirrors.aliyun.com/ros2/ubuntu' \
            'URIs: https://mirror.nju.edu.cn/ros2/ubuntu' \
            'URIs: http://mirrors.hit.edu.cn/ros2/ubuntu' \
            > /tmp/ros-apt-mirrors; \
        sed -i -e 's|^Types: .*|Types: deb|' -e '/^URIs:/r /tmp/ros-apt-mirrors' "${sources}"; \
        rm -f /tmp/ros-apt-mirrors; \
    else \
        sed -i -e 's|^Types: .*|Types: deb|' -e "s|^URIs: .*|URIs: ${ROS_APT_MIRROR}|" "${sources}"; \
    fi; \
    sed -n '1,6p' "${sources}"

RUN apt-get update -o Acquire::Retries=3 \
    && apt-get install -y --no-install-recommends \
        python3-pip \
        python3-venv \
        ros-jazzy-rmw-cyclonedds-cpp \
        ros-jazzy-example-interfaces \
        ros-jazzy-test-msgs \
    && rm -rf /var/lib/apt/lists/*

COPY --from=build /opt/ros/overlay /opt/ros/overlay
COPY --from=build /workspace/agent /opt/app/agent
COPY --from=build /workspace/mcp /opt/app/mcp
COPY --from=build /workspace/ros2_ws/config /opt/app/ros2_ws/config
COPY docker/package/entrypoint.sh /usr/local/bin/rtos-subhealth-entrypoint

RUN chmod +x /usr/local/bin/rtos-subhealth-entrypoint \
    && python3 -m venv /opt/app/mcp/.venv \
    && /opt/app/mcp/.venv/bin/pip install --no-cache-dir /opt/app/mcp \
    && python3 -m venv /opt/app/agent/.venv \
    && /opt/app/agent/.venv/bin/pip install --no-cache-dir /opt/app/agent

EXPOSE 5000
ENTRYPOINT ["/usr/local/bin/rtos-subhealth-entrypoint"]

FROM nginx:1.27-alpine AS frontend
COPY --from=build /workspace/webui/dist /usr/share/nginx/html
COPY docker/package/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
