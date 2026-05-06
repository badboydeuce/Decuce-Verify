FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install script
COPY requirements.txt .
COPY install.sh .

# Make install script executable and run
RUN chmod +x install.sh && ./install.sh

# Copy application
COPY . .

# Create logs directory
RUN mkdir -p logs

# Expose Flask port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# Start both services
CMD python api/app.py & python -m bot.main
