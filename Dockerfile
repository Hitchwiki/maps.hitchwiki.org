# Use a minimal Python image
FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && \
    apt-get install -y curl build-essential cron && \
    rm -rf /var/lib/apt/lists/*

# Install Node.js (LTS)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

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

# TODO: not working yet - does not place output file in app/dist persitently
# Get rides from Nostr
WORKDIR /app/hitch/scripts/fetch_hitchhiking_events
RUN npm install
RUN npx tsc
RUN node dist/index.js

WORKDIR /app

# Build frontend (if needed)
# RUN npm run build

RUN curl -fsSL https://hitchmap.com/dump.sqlite -o db/prod-points.sqlite

# Expose port (adjust if your server uses a different port)
EXPOSE 5000

# RUN ["python", "scripts/show.py", "service"]
# RUN ["python", "scripts/dashboard.py"]

# Install crontab from cron.sh
RUN crontab /app/cron.sh

# Start cron in background and run the server
CMD flask init &&service cron start && flask run --host=0.0.0.0 --port=5000