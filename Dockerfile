FROM python:3.11-slim@sha256:b7a9e5f6a93d6d4a31f129bbd4bdee69efccb6ded0fb230d78aafaf37af98377 AS engine
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_DEFAULT_TIMEOUT=120 PIP_RETRIES=10 OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 PYTHONPATH=/workspace
RUN apt-get update && apt-get install -y --no-install-recommends libxrender1 libxext6 libgomp1 libexpat1 libfreetype6 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /workspace
COPY pyproject.toml ./
COPY requirements.lock ./
COPY chemlab ./chemlab
RUN pip install --no-cache-dir -c requirements.lock .
COPY configs ./configs
ENTRYPOINT ["python", "-m", "chemlab"]
CMD ["serve", "--host", "0.0.0.0"]

FROM engine AS test
RUN pip install --no-cache-dir -c requirements.lock pytest httpx ruff mypy hypothesis pypdf
COPY tests ./tests
COPY scripts ./scripts
COPY start_venv.py start_docker.py ./
COPY compose.yaml Dockerfile ./
ENTRYPOINT ["python", "-m", "pytest"]
CMD ["-q", "--basetemp=/tmp/chemlab-tests"]

FROM test AS pretrained
RUN pip install --no-cache-dir -c requirements.lock torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -c requirements.lock '.[pretrained]'
ENTRYPOINT ["python", "-m", "chemlab"]
CMD ["serve", "--host", "0.0.0.0"]
