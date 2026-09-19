FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 PYTHONUNBUFFERED=1 HF_HOME=/opt/huggingface VF_EMBEDDING_MODEL_PATH=/opt/huggingface/models/intfloat/multilingual-e5-small
WORKDIR /app
ARG VF_EMBEDDING_REVISION=614241f622f53c4eeff9890bdc4f31cfecc418b3
COPY apps/embedding/pyproject.toml /app/apps/embedding/pyproject.toml
COPY apps/embedding /app/apps/embedding
RUN pip install --upgrade pip && pip install -e /app/apps/embedding \
    && python -c "from huggingface_hub import snapshot_download; snapshot_download('intfloat/multilingual-e5-small', revision='${VF_EMBEDDING_REVISION}', local_dir='/opt/huggingface/models/intfloat/multilingual-e5-small', allow_patterns=['onnx/model.onnx', 'onnx/config.json', 'onnx/tokenizer.json', 'onnx/tokenizer_config.json', 'onnx/special_tokens_map.json', 'onnx/sentencepiece.bpe.model'])" \
    && rm -rf /root/.cache
ENV TRANSFORMERS_OFFLINE=1 HF_HUB_OFFLINE=1
EXPOSE 8100
CMD ["uvicorn", "apps.embedding.main:app", "--host", "0.0.0.0", "--port", "8100"]
