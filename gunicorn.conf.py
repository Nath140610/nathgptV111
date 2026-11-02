"""Configuration Gunicorn pour Render : gunicorn --config gunicorn.conf.py server:app"""

import os

bind = f"0.0.0.0:{os.getenv('PORT', '10000')}"
worker_class = "uvicorn_worker.UvicornWorker"
# Un seul processus : les limites de débit et les générations en cours sont gardées en mémoire.
workers = 1
# Les réponses arrivent en streaming (SSE) et peuvent durer plusieurs minutes.
timeout = 360
graceful_timeout = 30
keepalive = 75
# Render termine le HTTPS devant l'application : on fait confiance à ses en-têtes X-Forwarded-*.
forwarded_allow_ips = "*"
accesslog = None
