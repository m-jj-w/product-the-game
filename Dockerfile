FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY engine ./engine
COPY agents ./agents
COPY server ./server
COPY cli ./cli
COPY data ./data
COPY rules ./rules

RUN pip install --no-cache-dir .

ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "uvicorn server.app:app --host 0.0.0.0 --port ${PORT}"]
