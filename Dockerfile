FROM python:3.12-slim

# WeasyPrint runtime dependencies (Cairo, Pango, Arabic fonts)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libgdk-pixbuf-xlib-2.0-0 \
    libffi-dev \
    shared-mime-info \
    fonts-arabeyes \
    fonts-hosny-amiri \
    fonts-noto-core \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install uv for super-fast package installation
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

COPY pyproject.toml .
RUN uv pip install --system -r pyproject.toml

COPY . .

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8000
