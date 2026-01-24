FROM ubuntu:24.04

ENV TZ=Asia/Tokyo
ENV DEBIAN_FRONTEND=noninteractive
ENV PATH="/home/ubuntu/.local/bin:$PATH"
ENV UV_LINK_MODE=copy

RUN apt-get update && apt-get install --assume-yes \
    curl \
    tini \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

RUN curl -O https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb

RUN apt-get update && apt-get install --assume-yes \
    language-pack-ja \
    python3 \
    smem \
    ffmpeg \
    ./google-chrome-stable_current_amd64.deb \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

RUN locale-gen en_US.UTF-8
RUN locale-gen ja_JP.UTF-8

# フォントをコピー
COPY font /usr/share/fonts/

RUN useradd -m ubuntu
USER ubuntu

WORKDIR /opt/price_watch

# uv をインストール
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

COPY --chown=ubuntu:ubuntu pyproject.toml uv.lock .python-version ./
RUN uv sync --no-group dev

COPY --chown=ubuntu:ubuntu . .

RUN mkdir -p data

ENTRYPOINT ["/usr/bin/tini", "--", "uv", "run", "--no-group", "dev"]
CMD ["price-watch"]
