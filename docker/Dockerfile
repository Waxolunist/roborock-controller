FROM python:3.14-bookworm AS builder

ENV PIP_NO_CACHE_DIR=off \
  PIP_DISABLE_PIP_VERSION_CHECK=on \
  POETRY_NO_INTERACTION=1 \
  POETRY_VIRTUALENVS_IN_PROJECT=1 \
  POETRY_VIRTUALENVS_CREATE=1 \
  POETRY_CACHE_DIR='/var/cache/pypoetry' \
  POETRY_VERSION=2.1.3

RUN pip install poetry==$POETRY_VERSION

WORKDIR /app
COPY poetry.lock pyproject.toml /app/
RUN touch README.md && poetry install --without dev --no-root && rm -rf $POETRY_CACHE_DIR

FROM python:3.14-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
  VIRTUAL_ENV=/app/.venv \
  PATH="/app/.venv/bin:$PATH" \
  PYTHONPATH=/app/src \
  ROBOROCK_SECRETS=/config/secrets.json \
  ROBOROCK_CACHE=/cache/roborock.cache

RUN useradd --system --uid 10001 --home /app roborock && mkdir /cache && chown roborock /cache

WORKDIR /app
COPY --from=builder ${VIRTUAL_ENV} ${VIRTUAL_ENV}
COPY src /app/src

USER roborock
EXPOSE 8080 9105
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health', timeout=4)"

ENTRYPOINT ["python", "-m", "roborock_controller"]
CMD ["serve"]
