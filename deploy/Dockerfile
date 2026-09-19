FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY winston ./winston
RUN pip install --no-cache-dir .
ENV PYTHONUNBUFFERED=1
# Mount the config directory holding winston.toml and zuliprc at /etc/winston.
CMD ["winston", "run", "--config", "/etc/winston/winston.toml"]
