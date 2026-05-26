FROM python:3.12-slim
RUN apt-get update && apt-get install -y cron && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY app.py newsletter-generator.py entrypoint.sh ./
RUN chmod +x entrypoint.sh
# Cron-Jobs: DS 07:00 UTC, KI 07:30 UTC (= 08:00 / 08:30 MESZ)
RUN echo "0 7 * * * root python3 /app/newsletter-generator.py ds >> /var/log/newsletter.log 2>&1" > /etc/cron.d/newsletter \
 && echo "30 7 * * * root python3 /app/newsletter-generator.py ki >> /var/log/newsletter.log 2>&1" >> /etc/cron.d/newsletter \
 && chmod 0644 /etc/cron.d/newsletter
EXPOSE 8080
CMD ["/app/entrypoint.sh"]
