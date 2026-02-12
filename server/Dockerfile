FROM python:3.10-slim

WORKDIR /app

# Install system dependencies (if any needed for psycopg2 or other libs)
# RUN apt-get update && apt-get install -y gcc libpq-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code into a package structure
COPY . ./server

# Expose port 8000
EXPOSE 8000

# Set python path
ENV PYTHONPATH=/app

# Command to run the application
CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8000"]
