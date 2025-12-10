# Pin to bookworm to keep FFmpeg at a version compatible with PyAV used by faster-whisper
FROM python:3.11-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        git \
        build-essential \
        curl \
        ffmpeg \
        pkg-config \
        libavdevice-dev \
        libavfilter-dev \
        libavformat-dev \
        libavutil-dev \
        libswresample-dev \
        libswscale-dev \
        libavcodec-dev \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspaces/speaking-stone-stack

RUN useradd -m -s /bin/bash devenv && chown -R devenv:devenv /workspaces

COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

USER devenv

CMD ["uvicorn", "speaking_stone_edge.main:app", "--host", "0.0.0.0", "--port", "8000"]
