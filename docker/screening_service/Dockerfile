FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DATA_DIR=/var/lib/screening

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY screening_service/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY screening_service /app/screening_service
COPY data /app/data

EXPOSE 8000

CMD ["uvicorn", "screening_service.main:app", "--host", "0.0.0.0", "--port", "8000"]
