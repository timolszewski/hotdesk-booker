FROM python:3.11-slim

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir requests flask flask-cors gunicorn

# Copy application
COPY booker.py app.py entrypoint.sh /app/
COPY templates /app/templates/
COPY static /app/static/

# Create directories for data and logs
RUN mkdir -p /app/data /app/logs

# Make scripts executable
RUN chmod +x /app/booker.py /app/entrypoint.sh

# Set timezone
ENV TZ=Europe/Warsaw
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Expose web UI port
EXPOSE 5000

# Default: run web UI with scheduler
ENTRYPOINT ["/app/entrypoint.sh"]
