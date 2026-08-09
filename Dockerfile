FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY config ./config
COPY core ./core
COPY parser ./parser
COPY bot ./bot
COPY main.py .

RUN pip install --no-cache-dir .

CMD ["python", "main.py"]
