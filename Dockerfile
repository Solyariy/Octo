FROM python:3.13-slim

WORKDIR /app

# Install uv for fast Python package management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files first for better layer caching
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-dev

# Copy application code
COPY src/ ./src/
COPY .env .env

# Expose the application port
EXPOSE 8000

# Run the FastAPI app with uvicorn
CMD ["uv", "run", "python", "-m", "src.main"]
