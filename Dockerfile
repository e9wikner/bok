FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create necessary directories
RUN mkdir -p scripts data

# Expose port
EXPOSE 8000

# Initialize database with test data, then start server
CMD ["sh", "-c", "python main.py --init-db --seed && python main.py --host 0.0.0.0 --port 8000"]
