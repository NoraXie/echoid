FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
# tzdata is needed for timezone configuration
RUN apt-get update && apt-get install -y tzdata && rm -rf /var/lib/apt/lists/*

COPY server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy entire project (server, tests, docs, etc.)
COPY . .

# Expose port 8000
EXPOSE 8000

# Set python path
ENV PYTHONPATH=/app

# Command to run the application
CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8000"]
