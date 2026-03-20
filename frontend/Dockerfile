FROM python:3.11-slim

WORKDIR /app

# Copy requirements from the root
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the frontend code
COPY frontend/ /app/frontend/

# Expose the Streamlit port
EXPOSE 8501

# Command to run the frontend
CMD ["streamlit", "run", "frontend/app.py", "--server.address", "0.0.0.0"]
