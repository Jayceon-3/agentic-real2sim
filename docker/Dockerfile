# Unattended experiment runner for AHa-3D.
# The image holds only system libraries. Blender, the Python venvs, model weights
# and Codex come from the host through read-only bind mounts at their original
# absolute paths (see scripts/exp_container.sh), so nothing is copied or rebuilt.
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates git ffmpeg imagemagick python3 procps bubblewrap less \
      # Blender 5.x runtime libraries
      libx11-6 libxi6 libxxf86vm1 libxfixes3 libxrender1 libxkbcommon0 \
      libxkbcommon-x11-0 libxcursor1 libxinerama1 libxrandr2 libsm6 libice6 \
      libgl1 libegl1 libglu1-mesa libwayland-client0 libwayland-cursor0 \
      libwayland-egl1 libdecor-0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Match the host user so git, paths under /home and file ownership line up.
# Build with: docker build --build-arg USERNAME=$(id -un) --build-arg USER_UID=$(id -u) -t aha3d-exp:latest docker/
# ubuntu:24.04 already has uid 1000 ("ubuntu"); reuse it when the host uid is 1000.
ARG USERNAME=dev
ARG USER_UID=1000
RUN if [ "$USER_UID" = "1000" ]; then \
      usermod -l "$USERNAME" -d "/home/$USERNAME" -m ubuntu && groupmod -n "$USERNAME" ubuntu; \
    else \
      useradd -m -u "$USER_UID" "$USERNAME"; \
    fi

USER $USERNAME
WORKDIR /home/$USERNAME
