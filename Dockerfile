# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables for Python
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set the working directory in the container
WORKDIR /app

# Install system dependencies if any (e.g., for database drivers)
# RUN apt-get update && apt-get install -y --no-install-recommends some-package && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
# Copy only requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
# Assuming your source code is in a 'src' directory relative to the Dockerfile
COPY src/ ./src/

# Copy the environment file (alternatively, pass vars at runtime)
# Ensure this doesn't contain secrets if the image is public!
# Using a placeholder name to avoid issues if .env is in .dockerignore
# The run script should rename/copy this to .env if needed or vars should be passed.
# COPY .env .env.docker # Example if using a file

# Expose ports used by FastAPI/Uvicorn and Streamlit
EXPOSE 8000
EXPOSE 8501

# Define the command to run the application
# Using a simple shell script to run both processes is common
# Create a startup script (start.sh) first
COPY start.sh .
RUN chmod +x ./start.sh

CMD ["./start.sh"] 