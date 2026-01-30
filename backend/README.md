# BarberScore POS Backend API

Professional PostgreSQL + Node.js/Express backend for the BarberScore POS system.

## Features

- ✅ PostgreSQL database with complete schema
- ✅ RESTful API with JWT authentication
- ✅ Multi-user support with role-based access control
- ✅ Customer relationship management
- ✅ Appointment scheduling
- ✅ Inventory management
- ✅ Transaction processing with multiple payment methods
- ✅ BarberScore algorithm calculation
- ✅ Comprehensive analytics endpoints
- ✅ Audit logging
- ✅ Cloud-ready (Railway, Render, AWS)

## Tech Stack

- **Backend**: Node.js + Express.js
- **Database**: PostgreSQL 14+
- **Authentication**: JWT (JSON Web Tokens)
- **Security**: Helmet, bcrypt, rate limiting
- **Validation**: Joi

## Quick Start

### 1. Prerequisites

- Node.js 18+ installed
- PostgreSQL 14+ installed and running
- npm or yarn

### 2. Installation

```bash
cd backend
npm install
```

### 3. Database Setup

Create a PostgreSQL database:

```bash
psql -U postgres
CREATE DATABASE barberscore_pos;
\q
```

Run the schema migration:

```bash
psql -U postgres -d barberscore_pos -f schema.sql
```

### 4. Environment Configuration

Copy `.env.example` to `.env` and update:

```bash
cp .env.example .env
```

Edit `.env`:

```env
DATABASE_URL=postgresql://postgres:your_password@localhost:5432/barberscore_pos
PORT=3000
NODE_ENV=development
JWT_SECRET=your-super-secret-jwt-key-change-this-in-production
CORS_ORIGIN=http://localhost:3000,https://pos-ivrc.vercel.app
```

### 5. Start Development Server

```bash
npm run dev
```

Server will run at `http://localhost:3000`

## API Endpoints

### Authentication

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| POST | `/api/auth/register` | Register new shop owner | No |
| POST | `/api/auth/login` | Login user | No |
| GET | `/api/auth/me` | Get current user | Yes |
| POST | `/api/auth/change-password` | Change password | Yes |

### Customers

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/api/customers` | Get all customers | Yes |
| GET | `/api/customers/:id` | Get customer by ID | Yes |
| POST | `/api/customers` | Create new customer | Yes |
| PATCH | `/api/customers/:id` | Update customer | Yes |
| DELETE | `/api/customers/:id` | Delete customer | Yes |
| GET | `/api/customers/:id/transactions` | Get customer transaction history | Yes |

### Transactions

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/api/transactions` | Get all transactions | Yes |
| GET | `/api/transactions/:id` | Get transaction by ID | Yes |
| POST | `/api/transactions` | Create new transaction (complete sale) | Yes |
| PATCH | `/api/transactions/:id` | Update transaction | Yes |
| DELETE | `/api/transactions/:id` | Delete transaction | Yes |

### Services

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/api/services` | Get all services | Yes |
| GET | `/api/services/:id` | Get service by ID | Yes |
| POST | `/api/services` | Create new service | Yes |
| PATCH | `/api/services/:id` | Update service | Yes |
| DELETE | `/api/services/:id` | Delete service | Yes |

### Barbers (Employees)

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/api/barbers` | Get all barbers | Yes |
| GET | `/api/barbers/:id` | Get barber by ID | Yes |
| GET | `/api/barbers/:id/performance` | Get barber performance metrics | Yes |
| POST | `/api/barbers` | Create new barber | Yes |
| PATCH | `/api/barbers/:id` | Update barber | Yes |
| DELETE | `/api/barbers/:id` | Delete barber | Yes |

### Appointments

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/api/appointments` | Get all appointments | Yes |
| GET | `/api/appointments/:id` | Get appointment by ID | Yes |
| POST | `/api/appointments` | Create new appointment | Yes |
| PATCH | `/api/appointments/:id` | Update appointment | Yes |
| DELETE | `/api/appointments/:id` | Delete appointment | Yes |

### Products (Inventory)

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/api/products` | Get all products | Yes |
| GET | `/api/products/:id` | Get product by ID | Yes |
| GET | `/api/products/:id/history` | Get inventory history | Yes |
| POST | `/api/products` | Create new product | Yes |
| POST | `/api/products/:id/adjust` | Adjust inventory | Yes |
| PATCH | `/api/products/:id` | Update product | Yes |
| DELETE | `/api/products/:id` | Delete product | Yes |

### Analytics

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/api/analytics/dashboard` | Get dashboard summary | Yes |
| GET | `/api/analytics/sales-by-period` | Get sales by day/week/month | Yes |
| GET | `/api/analytics/top-services` | Get top performing services | Yes |
| GET | `/api/analytics/top-customers` | Get top customers | Yes |
| GET | `/api/analytics/barber-leaderboard` | Get barber performance rankings | Yes |
| GET | `/api/analytics/payment-methods` | Get payment method breakdown | Yes |
| GET | `/api/analytics/barberscore` | Calculate BarberScore | Yes |

### Shops

| Method | Endpoint | Description | Auth Required | Roles |
|--------|----------|-------------|---------------|-------|
| GET | `/api/shops` | Get all shops | Yes | admin |
| GET | `/api/shops/:id` | Get shop by ID | Yes | owner, admin |
| PATCH | `/api/shops/:id` | Update shop | Yes | owner, admin |
| DELETE | `/api/shops/:id` | Delete shop | Yes | admin |

## Database Schema

The database includes the following main tables:

- **users** - User accounts with authentication
- **shops** - Shop/location information
- **customers** - Customer profiles with preferences
- **barbers** - Employee profiles and commission rates
- **services** - Service catalog
- **transactions** - Sales records with BarberScore tracking
- **transaction_items** - Line items for each transaction
- **appointments** - Appointment scheduling
- **appointment_services** - Services linked to appointments
- **products** - Inventory items
- **inventory_transactions** - Inventory change log
- **barberscore_metrics** - Historical score calculations
- **audit_logs** - System audit trail

See `schema.sql` for complete database schema with indexes and views.

## Deployment

### Deploy to Railway

1. Create account at [Railway.app](https://railway.app)
2. Create new project
3. Add PostgreSQL database
4. Add new service from GitHub repo
5. Set environment variables:
   ```
   DATABASE_URL=(automatically set by Railway)
   JWT_SECRET=your-secret-key
   NODE_ENV=production
   CORS_ORIGIN=https://pos-ivrc.vercel.app
   ```
6. Deploy!

### Deploy to Render

1. Create account at [Render.com](https://render.com)
2. Create new PostgreSQL database
3. Create new Web Service
4. Connect GitHub repo
5. Set build command: `npm install`
6. Set start command: `npm start`
7. Add environment variables
8. Deploy!

### Deploy to AWS (EC2 + RDS)

1. Create RDS PostgreSQL instance
2. Create EC2 instance
3. SSH into EC2 and clone repo
4. Install Node.js and PostgreSQL client
5. Run database migration
6. Configure `.env` with RDS connection string
7. Use PM2 for process management:
   ```bash
   npm install -g pm2
   pm2 start src/server.js --name barberscore-api
   pm2 startup
   pm2 save
   ```

## Security Best Practices

- ✅ All passwords hashed with bcrypt
- ✅ JWT tokens for authentication
- ✅ Rate limiting on all API routes
- ✅ Helmet.js for security headers
- ✅ CORS configured for specific origins
- ✅ SQL injection protection (parameterized queries)
- ✅ Role-based access control
- ✅ Audit logging for all sensitive operations

## Testing

Test the health endpoint:

```bash
curl http://localhost:3000/health
```

Expected response:
```json
{
  "status": "healthy",
  "timestamp": "2025-01-30T...",
  "database": "connected"
}
```

## Migration from localStorage

To migrate existing localStorage data to the database:

1. Export data from frontend (Settings > Export Data)
2. Use migration script (coming soon) to import
3. Update frontend to use API instead of localStorage

## Support

For issues or questions:
- Check the API documentation above
- Review error messages in console
- Ensure PostgreSQL is running and accessible
- Verify environment variables are set correctly

## License

MIT
