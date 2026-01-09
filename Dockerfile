FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/app/.cache/huggingface \
    KOBERT_MODEL_ID=skt/kobert-base-v1

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

RUN python - <<'PY'
from transformers import AutoModel, AutoTokenizer
model_id = "skt/kobert-base-v1"
AutoTokenizer.from_pretrained(model_id)
AutoModel.from_pretrained(model_id)
PY

COPY . /app
