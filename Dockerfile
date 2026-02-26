FROM python:3.11-slim

# Install git and build dependencies for Qlib/LightGBM
RUN apt-get update && apt-get install -y \
    git \
    build-essential \
    g++ \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Ensure logs are not buffered
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Run the scheduler
CMD ["python", "backend/run_loop.py"]
