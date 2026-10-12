FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files and syllabus data
COPY slack_bot.py .
COPY src/data/syllabus.json ./src/data/syllabus.json
COPY .env* .

# Run Slack Bot in Socket Mode
CMD ["python", "-u", "slack_bot.py"]
