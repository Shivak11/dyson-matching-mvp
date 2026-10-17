FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app_server.py runtime_config.json ./
COPY webapp ./webapp
COPY web/index.html web/style.css web/app.js ./web/
COPY cloudflare/seed/catalogue-seed ./var/catalogue-seed
COPY cloudflare/seed/runtime ./var/runtime
ENV PYTHONUNBUFFERED=1
EXPOSE 8080
CMD ["python", "app_server.py", "--port", "8080"]
