# Use a minimal Python image
FROM python:3.12-slim

# Install system dependencies
# rclone is used by the weekly backup_to_drive.py job to upload to Google Drive
RUN apt-get update && \
    apt-get install -y curl build-essential cron rclone && \
    rm -rf /var/lib/apt/lists/*

# Install Node.js (LTS) and upgrade npm
RUN curl -fsSL https://deb.nodesource.com/setup_24.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/* && \
    npm install -g npm@12.0.0

# Set work directory
WORKDIR /app

# Copy Python requirements and install
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the code
COPY . .

# Build the Nostr fetch scripts (TypeScript -> dist/index.js, dist/index_incremental.js).
# node_modules/ and dist/ are .dockerignore'd, so they are NOT copied from the build context
# and must be produced here, in the image. fetch_nostr / fetch_nostr_incremental run these.
WORKDIR /app/hitch/scripts/fetch_hitchhiking_events
RUN npm ci && npm run build
WORKDIR /app

# Expose port (adjust if your server uses a different port)
EXPOSE 4242

# RUN ["python", "scripts/show.py", "service"]
# RUN ["python", "scripts/dashboard.py"]

# Install crontab from cron.sh
RUN crontab /app/deploy/cron.sh

# Start cron in background and run the server
CMD ["sh", "deploy/run.sh"]