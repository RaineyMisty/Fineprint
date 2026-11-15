FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY fineprint ./fineprint
RUN pip install --no-cache-dir . && rm -rf /root/.cache /tmp/pip-*

# The DeepSeek key must be provided at runtime via DEEPSEEK_API_KEY.
# Never bake credentials into the image.
ENV PYTHONUNBUFFERED=1
EXPOSE 8080
CMD ["python", "-m", "fineprint.server", "--host", "0.0.0.0", "--port", "8080"]
