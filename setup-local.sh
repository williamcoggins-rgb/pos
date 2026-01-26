#!/bin/bash

# BarberScore POS - Local Setup Script
# This script creates your .env file with the correct credentials

echo "================================================"
echo "  BarberScore POS - Local Environment Setup"
echo "================================================"
echo ""
echo "This script will help you configure your local environment."
echo "Have your Supabase and Stripe credentials ready!"
echo ""

# Check if .env already exists
if [ -f .env ]; then
    echo "⚠️  .env file already exists!"
    read -p "Do you want to overwrite it? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Setup cancelled. Existing .env file preserved."
        exit 0
    fi
fi

echo "---"
echo "Step 1: Supabase Credentials"
echo "---"
echo ""

read -p "Supabase Project URL (https://xxxxx.supabase.co): " SUPABASE_URL
read -p "Supabase Database URL (postgresql://...): " DATABASE_URL
read -p "Supabase Anon Key (eyJhbG...): " SUPABASE_KEY
read -p "Supabase JWT Secret: " SUPABASE_JWT_SECRET

echo ""
echo "---"
echo "Step 2: Stripe Credentials"
echo "---"
echo ""

read -p "Stripe Secret Key (sk_test_...): " STRIPE_SECRET_KEY
read -p "Stripe Publishable Key (pk_test_...): " STRIPE_PUBLISHABLE_KEY

echo ""
echo "---"
echo "Step 3: Security Settings"
echo "---"
echo ""

# Generate random secret key
SECRET_KEY=$(openssl rand -hex 32 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(32))")

echo "Generated secure SECRET_KEY: ${SECRET_KEY:0:16}..."

# Create .env file
cat > .env << EOF
# Database
DATABASE_URL=$DATABASE_URL

# Stripe
STRIPE_SECRET_KEY=$STRIPE_SECRET_KEY
STRIPE_PUBLISHABLE_KEY=$STRIPE_PUBLISHABLE_KEY

# Supabase
SUPABASE_URL=$SUPABASE_URL
SUPABASE_KEY=$SUPABASE_KEY
SUPABASE_JWT_SECRET=$SUPABASE_JWT_SECRET

# Security
SECRET_KEY=$SECRET_KEY
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# API Settings
DEBUG=true
API_VERSION=1.0.0
EOF

echo ""
echo "================================================"
echo "  ✅ Setup Complete!"
echo "================================================"
echo ""
echo "Your .env file has been created with your credentials."
echo ""
echo "Next steps:"
echo "  1. Start the API:     uvicorn api.main:app --reload"
echo "  2. Serve the UI:      cd web && python -m http.server 8080"
echo "  3. Open browser to:   http://localhost:8080/app.html"
echo ""
echo "Or use Docker:"
echo "  docker-compose up"
echo ""
echo "Full guide: See LOCAL_SETUP.md"
echo ""
