# Use official Python image as base
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code and assets (font, weather symbols)
COPY src/ ./src/
COPY scripts/server.py ./scripts/
COPY assets/ ./assets/

# config/ and data/ are created at runtime; mount config/ as a volume to keep credentials
EXPOSE 8000

CMD ["python", "scripts/server.py"]
