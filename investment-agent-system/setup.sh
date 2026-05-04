#!/usr/bin/env bash
# One-time setup script — run this once before starting the app.
set -e

echo "=== Investment Agent System — Setup ==="

# 1. Python version check
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "Python: $python_version"

# 2. Create .env if it does not exist
if [ ! -f .env ]; then
  cp .env.example .env
  echo ".env created from .env.example (edit it to add your API keys)"
else
  echo ".env already exists, skipping"
fi

# 3. Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt -q

# 4. Seed demo data
echo "Seeding demo data..."
PYTHONPATH=. python scripts/seed_demo_data.py

echo ""
echo "=== Setup complete! ==="
echo "Now run:  ./start.sh"
