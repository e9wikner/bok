FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (curl for healthcheck, git for version info, weasyprint deps for PDF)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git \
    libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 \
    libffi-dev libcairo2 libglib2.0-0 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application (including .git for version tracking)
COPY . .

# Create necessary directories
RUN mkdir -p scripts data

# Expose port
EXPOSE 8000

# Initialize database with test data, then start server
CMD ["sh", "-c", "python main.py --init-db --seed && python main.py --host 0.0.0.0 --port 8000"]
