FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for OCR and image processing
# libglib2.0-0 is often required by OpenCV even in its headless version
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-fra \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements from the root
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the backend code
COPY backend/ /app/backend/

# Set the python path to include the root so imports like 'from backend.app...' work
ENV PYTHONPATH=/app

# Expose the API port
EXPOSE 8000

# Command to run the backend
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
