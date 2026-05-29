FROM python:3.12-slim
RUN apt-get update && apt-get install -y cron && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY app.py newsletter-generator.py ./
# Cron-Jobs: DS 06:00 UTC, KI 06:30 UTC (= 08:00 / 08:30 MESZ)
RUN echo "0 6 * * * root bash -c '. /etc/environment && python3 /app/newsletter-generator.py ds >> /proc/1/fd/1 2>&1'" > /etc/cron.d/newsletter \
 && echo "30 6 * * * root bash -c '. /etc/environment && python3 /app/newsletter-generator.py ki >> /proc/1/fd/1 2>&1'" >> /etc/cron.d/newsletter \
 && echo "" >> /etc/cron.d/newsletter \
 && chmod 0644 /etc/cron.d/newsletter
EXPOSE 8080
CMD ["sh", "-c", "printenv | grep -E 'NEWSLETTER|AZURE|SMTP|ANTHROPIC' > /etc/environment; cron; exec python3 app.py"]
