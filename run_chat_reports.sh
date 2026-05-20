#!/bin/bash
# Weekly chat report generation
# Cron: 0 5 * * 1 /opt/kidion/run_chat_reports.sh >> /var/log/kidion-reports.log 2>&1
cd /opt/kidion
source venv/bin/activate
python -c "from services.chat_report import run_weekly_reports; run_weekly_reports()"
