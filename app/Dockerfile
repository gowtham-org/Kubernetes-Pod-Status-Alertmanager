FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
RUN useradd -m appuser
USER appuser

ENV DATA_DIR=/data
EXPOSE 8080

CMD ["python", "app.py"]