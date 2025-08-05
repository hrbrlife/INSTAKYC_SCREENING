FROM python:3.11-slim

ARG ZAVOD_VERSION=latest

RUN pip install --no-cache-dir "zavod==${ZAVOD_VERSION}"

WORKDIR /app

ENTRYPOINT ["zavod"]
CMD ["--help"]
