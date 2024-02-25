FROM python:3.10-slim

RUN apt update && apt install -y git netcat-traditional nodejs npm
RUN npm install npm@latest -g

EXPOSE 8000
WORKDIR /app
