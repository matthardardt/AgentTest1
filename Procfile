web: uvicorn store.main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips="*"
worker: python orchestrator.py
