FROM python:3.11-slim

WORKDIR /app

ENV POETRY_VIRTUALENVS_CREATE=false

RUN pip install pipx==1.2.0 --user --no-cache
RUN pipx install poetry==1.5.1

COPY [ "poetry.toml", "poetry.lock", "pyproject.toml", "./" ]
COPY src .

RUN poetry install --only main

ARG APP_VERSION
ENV BUILD_SHA=$APP_VERSION

ENTRYPOINT [ "python", "-m", "probability.bot" ]
