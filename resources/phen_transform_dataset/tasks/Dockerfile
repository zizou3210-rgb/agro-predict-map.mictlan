FROM python:3.12.4-slim-bookworm

WORKDIR /app

COPY requirements.txt .

RUN pip install -r requirements.txt

COPY src src/

COPY tasks.py .

COPY tasks_test.py .

COPY run.sh .

RUN chmod +x run.sh

ENTRYPOINT sh ./run.sh

