# Shared demo (demo/server.py) for Cloud Run. Copies ONLY what the server imports: no cases, runs,
# user-study data, docs or .git. See deploy/README.md.
FROM python:3.11-slim
WORKDIR /app
COPY deploy/requirements-demo.txt .
RUN pip install --no-cache-dir -r requirements-demo.txt
COPY meal/ meal/
COPY eval/__init__.py eval/pricing.py eval/
COPY data/ data/
COPY data_wm/ data_wm/
COPY demo/server.py demo/index.html demo/shell.html demo/
ARG CODE_REV=unknown
ENV CODE_REV=$CODE_REV HOST=0.0.0.0 DEMO_STORE=firestore PYTHONUNBUFFERED=1
CMD ["python", "demo/server.py"]
