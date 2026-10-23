FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1

RUN useradd --uid 1000 --create-home appuser

WORKDIR /app
COPY webhook.py /app/webhook.py

USER 1000

EXPOSE 8080

CMD ["python", "/app/webhook.py"]
