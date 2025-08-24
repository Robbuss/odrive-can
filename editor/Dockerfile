# Debian (ARM64-friendly) with Python 3.11 + Node 20 + Docker CLI + sudo + zsh
FROM debian:bookworm-slim

ARG DEBIAN_FRONTEND=noninteractive
ENV LANG=en_US.UTF-8 LANGUAGE=en_US:en LC_ALL=en_US.UTF-8 EDITOR=nano

# Base tools, Python, build tools, locales
RUN set -eux; \
  apt-get update; \
  apt-get install -y --no-install-recommends \
    bash zsh nano sudo git git-lfs ca-certificates curl wget gnupg \
    locales tzdata \
    python3 python3-pip python3-venv python3-dev \
    build-essential pkg-config \
    openssh-client; \  
  echo "en_US.UTF-8 UTF-8" >> /etc/locale.gen; \
  locale-gen en_US.UTF-8; \
  git lfs install --system

# Node.js 20 (multi-arch)
RUN set -eux; \
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -; \
  apt-get install -y --no-install-recommends nodejs; \
  npm -g i pnpm@9 yarn typescript ts-node

# Docker CLI + buildx + compose plugin (client only)
RUN set -eux; \
  install -m 0755 -d /etc/apt/keyrings; \
  curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg; \
  chmod a+r /etc/apt/keyrings/docker.gpg; \
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian bookworm stable" \
    > /etc/apt/sources.list.d/docker.list; \
  apt-get update; \
  apt-get install -y --no-install-recommends docker-ce-cli docker-buildx-plugin docker-compose-plugin; \
  apt-get clean; rm -rf /var/lib/apt/lists/*

ARG DEV_USER=robbus
ARG DEV_UID=1000
ARG DEV_GID=1000
RUN groupadd -g "${DEV_GID}" "${DEV_USER}" \
 && useradd -m -u "${DEV_UID}" -g "${DEV_GID}" -s /bin/bash "${DEV_USER}" \
 && echo "${DEV_USER} ALL=(ALL) NOPASSWD:ALL" >/etc/sudoers.d/${DEV_USER} \
 && chmod 0440 /etc/sudoers.d/${DEV_USER}
WORKDIR /app
USER ${DEV_USER}
CMD ["bash","-lc","echo 'Editor ready as $(whoami)'; sleep infinity"]