FROM python:3.13-slim

WORKDIR /app

RUN pip install --no-cache-dir flask requests pytz

COPY *.py ./
