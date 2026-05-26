FROM python:3.12-slim
RUN apt-get update && apt-get install -y cron && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY app.py newsletter-generator.py ./
# Cron-Jobs: DS 07:00 UTC, KI 07:30 UTC (= 08:00 / 08:30 MESZ)
RUN echo "0 7 * * * root python3 /app/newsletter-generator.py ds >> /var/log/newsletter.log 2>&1" > /etc/cron.d/newsletter \
 && echo "30 7 * * * root python3 /app/newsletter-generator.py ki >> /var/log/newsletter.log 2>&1" >> /etc/cron.d/newsletter \
 && chmod 0644 /etc/cron.d/newsletter
# Entrypoint direkt im Dockerfile (vermeidet CRLF-Probleme mit Shell-Skripten)
RUN printf '#!/bin/sh\nprintenv | grep -E "NEWSLETTER_WEBHOOK_TOKEN|AZURE_|SMTP_" >> /etc/environment\ncron\nexec python app.py\n' > /app/start.sh \
 && chmod +x /app/start.sh
EXPOSE 8080
CMD ["/app/start.sh"]
