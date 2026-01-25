FROM ubuntu:24.04@sha256:c35e29c9450151419d9448b0fd75374fec4fff364a27f176fb458d472dfc9e54

# NOTE:
# python:3.11.4-bookworm とかを使った場合，Selenium を同時に複数動かせないので，
# Ubuntu イメージを使う

RUN --mount=type=cache,target=/var/lib/apt,sharing=locked \
    --mount=type=cache,target=/var/cache/apt,sharing=locked \
    apt-get update && apt-get install --no-install-recommends --assume-yes \
    curl \
    ca-certificates \
    tini \
    build-essential \
    git \
    language-pack-ja \
    tzdata \
    fonts-noto-cjk \
    smem \
    ffmpeg

ENV TZ=Asia/Tokyo \
    LANG=ja_JP.UTF-8 \
    LANGUAGE=ja_JP:ja \
    LC_ALL=ja_JP.UTF-8

RUN locale-gen en_US.UTF-8
RUN locale-gen ja_JP.UTF-8

# NOTE: Chrome 143 でレンダラープロセスが約20分後に切断される問題があるため、Chrome 142 に固定
RUN curl -O https://dl.google.com/linux/chrome/deb/pool/main/g/google-chrome-stable/google-chrome-stable_142.0.7444.175-1_amd64.deb

RUN --mount=type=cache,target=/var/lib/apt,sharing=locked \
    --mount=type=cache,target=/var/cache/apt,sharing=locked \
    apt-get update && apt-get install --no-install-recommends --assume-yes \
    ./google-chrome-stable_142.0.7444.175-1_amd64.deb


COPY font /usr/share/fonts/
RUN fc-cache --force --verbose

USER ubuntu

ENV PYTHONDONTWRITEBYTECODE=1
ENV PATH="/home/ubuntu/.local/bin:$PATH"
ENV UV_LINK_MODE=copy

# ubuntu ユーザーで uv をインストール
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

WORKDIR /opt/price_watch

RUN --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=.python-version,target=.python-version \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=README.md,target=README.md \
    --mount=type=bind,source=src,target=src \
    --mount=type=bind,source=.git,target=.git \
    --mount=type=cache,target=/home/ubuntu/.cache/uv,uid=1000,gid=1000 \
    git config --global --add safe.directory /opt/price_watch && \
    uv sync --no-editable --no-group dev

ARG IMAGE_BUILD_DATE
ENV IMAGE_BUILD_DATE=${IMAGE_BUILD_DATE}

COPY --chown=ubuntu:ubuntu . .

RUN mkdir -p data

ENTRYPOINT ["/usr/bin/tini", "--", "uv", "run", "--no-group", "dev"]

CMD ["price-watch"]
