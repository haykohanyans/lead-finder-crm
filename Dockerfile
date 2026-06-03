FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Railway sets PORT env var - app must bind to it
# We use python app.py which reads PORT from env
CMD ["python", "app.py"]
