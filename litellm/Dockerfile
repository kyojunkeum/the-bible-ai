FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir "litellm[proxy]"

ENTRYPOINT ["litellm"]
CMD ["--config", "/app/config.yaml", "--port", "4000", "--host", "0.0.0.0"]
