FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app/agents

RUN pip install --no-cache-dir google-adk==1.26.0

CMD ["adk", "api_server", "--host", "0.0.0.0", "--port", "8000"]
