#!/bin/bash
# BarberScore POS Backend - Quick Deploy to Railway
# Run this after deploying to Railway to verify everything works

echo "================================"
echo "BarberScore POS - Deployment Test"
echo "================================"
echo ""

# Get Railway URL from user
read -p "Enter your Railway API URL (e.g., https://your-project.up.railway.app): " RAILWAY_URL

# Remove trailing slash if present
RAILWAY_URL="${RAILWAY_URL%/}"

echo ""
echo "Testing connection to: $RAILWAY_URL"
echo ""

# Test 1: Health Check
echo "Test 1: Health Check"
echo "--------------------"
HEALTH_RESPONSE=$(curl -s "$RAILWAY_URL/health")
echo $HEALTH_RESPONSE | jq '.' 2>/dev/null || echo $HEALTH_RESPONSE
echo ""

# Test 2: Register Test User
echo "Test 2: Register Test User"
echo "---------------------------"
REGISTER_RESPONSE=$(curl -s -X POST "$RAILWAY_URL/api/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@barberscore.com",
    "password": "test12345",
    "shopName": "Test Barbershop",
    "ownerName": "Test Owner",
    "phone": "(555) 123-4567"
  }')

echo $REGISTER_RESPONSE | jq '.' 2>/dev/null || echo $REGISTER_RESPONSE

# Extract token
TOKEN=$(echo $REGISTER_RESPONSE | jq -r '.token' 2>/dev/null)

if [ "$TOKEN" != "null" ] && [ "$TOKEN" != "" ]; then
    echo ""
    echo "✅ Registration successful!"
    echo "Token: ${TOKEN:0:20}..."
    echo ""

    # Test 3: Get Current User
    echo "Test 3: Get Current User"
    echo "-------------------------"
    USER_RESPONSE=$(curl -s "$RAILWAY_URL/api/auth/me" \
      -H "Authorization: Bearer $TOKEN")
    echo $USER_RESPONSE | jq '.' 2>/dev/null || echo $USER_RESPONSE
    echo ""

    # Test 4: Create Service
    echo "Test 4: Create Service"
    echo "----------------------"
    SERVICE_RESPONSE=$(curl -s -X POST "$RAILWAY_URL/api/services" \
      -H "Authorization: Bearer $TOKEN" \
      -H "Content-Type: application/json" \
      -d '{
        "name": "Haircut",
        "price": 30.00,
        "duration_minutes": 30,
        "category": "haircut"
      }')
    echo $SERVICE_RESPONSE | jq '.' 2>/dev/null || echo $SERVICE_RESPONSE
    echo ""

    # Test 5: Get Services
    echo "Test 5: Get Services"
    echo "--------------------"
    SERVICES_RESPONSE=$(curl -s "$RAILWAY_URL/api/services" \
      -H "Authorization: Bearer $TOKEN")
    echo $SERVICES_RESPONSE | jq '.' 2>/dev/null || echo $SERVICES_RESPONSE
    echo ""

    echo "================================"
    echo "✅ All tests passed!"
    echo "================================"
    echo ""
    echo "Your backend is ready to use!"
    echo "API URL: $RAILWAY_URL/api"
    echo ""
    echo "Next steps:"
    echo "1. Update web/api-service.js with your Railway URL"
    echo "2. Open web/migrate-data.html to migrate your data"
    echo "3. Start using the new backend!"
else
    echo ""
    echo "❌ Registration failed. Check your deployment:"
    echo "- Is the database connected?"
    echo "- Did you run the schema migration?"
    echo "- Check Railway logs for errors"
fi
