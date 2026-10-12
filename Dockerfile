FROM python:3.12-slim
LABEL maintainer="leiyang <leiyang753@gmail.com>"

ENV PYTHONUNBUFFERED=1

WORKDIR /code

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENTRYPOINT ["python3", "checkin.py"]
