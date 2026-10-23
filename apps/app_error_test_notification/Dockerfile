FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1

RUN useradd --uid 1000 --create-home appuser

WORKDIR /app
COPY app.py /app/app.py

USER 1000

EXPOSE 8080

CMD ["python", "/app/app.py"]
