FROM python:3.12-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq-dev gcc curl build-essential && \
    rm -rf /var/lib/apt/lists/*
    
RUN curl -sSL https://install.python-poetry.org | python3 -
ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

COPY pyproject.toml poetry.lock ./

RUN poetry install --no-root --no-cache

COPY . .

CMD ["poetry", "run", "python", "main.py"]
