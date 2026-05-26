#!/bin/bash
# Startet cron + Webhook-Server
printenv | grep -E "NEWSLETTER_WEBHOOK_TOKEN|AZURE_|SMTP_" >> /etc/environment
cron
exec python app.py
