# Use a minimal Python image
FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && \
    apt-get install -y curl build-essential cron && \
    rm -rf /var/lib/apt/lists/*

# Install Node.js (LTS) and upgrade npm
RUN curl -fsSL https://deb.nodesource.com/setup_24.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/* && \
    npm install -g npm@11.18.0

# Set work directory
WORKDIR /app

# Copy Python requirements and install
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy package.json and install Node dependencies
# COPY package.json ./
# RUN npm install

# Copy the rest of the code
COPY . .

# Expose port (adjust if your server uses a different port)
EXPOSE 4242

# RUN ["python", "scripts/show.py", "service"]
# RUN ["python", "scripts/dashboard.py"]

# Install crontab from cron.sh
RUN crontab /app/deploy/cron.sh

# Start cron in background and run the server
CMD ["sh", "deploy/run.sh"]