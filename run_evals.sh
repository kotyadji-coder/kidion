#!/bin/bash
cd /opt/kidion
source venv/bin/activate
export $(grep -v "^#" .env | xargs)

# Check real user-generated lessons (cheap, ~$0.01/lesson)
python -m evals check >> /opt/kidion/logs/evals.log 2>&1
