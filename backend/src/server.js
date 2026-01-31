const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const morgan = require('morgan');
const rateLimit = require('express-rate-limit');
require('dotenv').config();

// Import routes
const authRoutes = require('./routes/auth');
const customerRoutes = require('./routes/customers');
const transactionRoutes = require('./routes/transactions');
const serviceRoutes = require('./routes/services');
const barberRoutes = require('./routes/barbers');
const appointmentRoutes = require('./routes/appointments');
const productRoutes = require('./routes/products');
const analyticsRoutes = require('./routes/analytics');
const shopRoutes = require('./routes/shops');
const paymentRoutes = require('./routes/payments');
const stripeOnboardingRoutes = require('./routes/stripe-onboarding');

// Import database
const { pool } = require('./config/database');

const app = express();
const PORT = process.env.PORT || 3000;

// ============================================
// MIDDLEWARE
// ============================================

// Security headers
app.use(helmet());

// CORS configuration
const corsOptions = {
    origin: process.env.CORS_ORIGIN ? process.env.CORS_ORIGIN.split(',') : '*',
    credentials: true,
    optionsSuccessStatus: 200
};
app.use(cors(corsOptions));

// Rate limiting
const limiter = rateLimit({
    windowMs: parseInt(process.env.RATE_LIMIT_WINDOW_MS) || 15 * 60 * 1000, // 15 minutes
    max: parseInt(process.env.RATE_LIMIT_MAX_REQUESTS) || 100,
    message: 'Too many requests from this IP, please try again later.'
});
app.use('/api/', limiter);

// Logging
if (process.env.NODE_ENV === 'development') {
    app.use(morgan('dev'));
} else {
    app.use(morgan('combined'));
}

// Body parsing
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// ============================================
// ROUTES
// ============================================

// Health check
app.get('/health', async (req, res) => {
    try {
        await pool.query('SELECT 1');
        res.json({
            status: 'healthy',
            timestamp: new Date().toISOString(),
            database: 'connected'
        });
    } catch (error) {
        res.status(503).json({
            status: 'unhealthy',
            timestamp: new Date().toISOString(),
            database: 'disconnected',
            error: error.message
        });
    }
});

// API routes
app.use('/api/auth', authRoutes);
app.use('/api/customers', customerRoutes);
app.use('/api/transactions', transactionRoutes);
app.use('/api/services', serviceRoutes);
app.use('/api/barbers', barberRoutes);
app.use('/api/appointments', appointmentRoutes);
app.use('/api/products', productRoutes);
app.use('/api/analytics', analyticsRoutes);
app.use('/api/shops', shopRoutes);
app.use('/api/payments', paymentRoutes);
app.use('/api/stripe', stripeOnboardingRoutes);

// Database setup routes
app.get('/add-stripe-fields', async (req, res) => {
    try {
        const fs = require('fs');
        const path = require('path');

        const migrationPath = path.join(__dirname, '../add-stripe-field.sql');
        const migration = fs.readFileSync(migrationPath, 'utf8');

        await pool.query(migration);

        res.send('<h1>✅ Stripe fields added successfully!</h1>');
    } catch (error) {
        console.error('Migration error:', error);
        res.status(500).send(`<h1>❌ Error: ${error.message}</h1>`);
    }
});

app.get('/setup', async (req, res) => {
    try {
        const fs = require('fs');
        const path = require('path');

        // Read schema file
        const schemaPath = path.join(__dirname, '../schema.sql');
        const schema = fs.readFileSync(schemaPath, 'utf8');

        // Execute schema
        await pool.query(schema);

        res.send(`
<!DOCTYPE html>
<html>
<head>
    <title>Database Setup Complete</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            margin: 0;
        }
        .container {
            background: white;
            border-radius: 20px;
            padding: 40px;
            max-width: 600px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }
        h1 { color: #4CAF50; margin-bottom: 20px; }
        p { color: #555; line-height: 1.6; }
        ul { color: #555; line-height: 1.8; }
        .success { color: #4CAF50; font-size: 48px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="success">✅</div>
        <h1>Database Setup Complete!</h1>
        <p>All database tables have been created successfully.</p>
        <h3>Tables Created:</h3>
        <ul>
            <li>Users & Authentication</li>
            <li>Shops & Locations</li>
            <li>Customers</li>
            <li>Barbers (Employees)</li>
            <li>Services</li>
            <li>Appointments</li>
            <li>Transactions (Sales)</li>
            <li>Transaction Items</li>
            <li>Products (Inventory)</li>
            <li>Inventory Transactions</li>
            <li>BarberScore Metrics</li>
            <li>Audit Logs</li>
        </ul>
        <p><strong>Your POS backend is ready to use!</strong></p>
    </div>
</body>
</html>
        `);
    } catch (error) {
        console.error('Database setup error:', error);
        res.status(500).send(`
<!DOCTYPE html>
<html>
<head>
    <title>Database Setup Error</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #f44336 0%, #e91e63 100%);
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            margin: 0;
        }
        .container {
            background: white;
            border-radius: 20px;
            padding: 40px;
            max-width: 600px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }
        h1 { color: #f44336; }
        p { color: #555; }
        code { background: #f5f5f5; padding: 2px 6px; border-radius: 4px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>❌ Database Setup Error</h1>
        <p><strong>Error:</strong> ${error.message}</p>
        <p>The database tables may already exist, or there might be a connection issue.</p>
    </div>
</body>
</html>
        `);
    }
});

// 404 handler
app.use((req, res) => {
    res.status(404).json({
        error: 'Not Found',
        message: `Route ${req.originalUrl} not found`
    });
});

// Global error handler
app.use((err, req, res, next) => {
    console.error('Error:', err);

    // Don't leak error details in production
    const errorResponse = {
        error: err.name || 'Internal Server Error',
        message: process.env.NODE_ENV === 'development' ? err.message : 'An error occurred',
    };

    if (process.env.NODE_ENV === 'development') {
        errorResponse.stack = err.stack;
    }

    res.status(err.statusCode || 500).json(errorResponse);
});

// ============================================
// START SERVER
// ============================================

app.listen(PORT, () => {
    console.log(`
╔═══════════════════════════════════════════════╗
║   BarberScore POS API Server                  ║
║   Environment: ${process.env.NODE_ENV || 'development'}                      ║
║   Port: ${PORT}                                   ║
║   URL: http://localhost:${PORT}                ║
╚═══════════════════════════════════════════════╝
    `);
});

// Graceful shutdown
process.on('SIGTERM', async () => {
    console.log('SIGTERM signal received: closing HTTP server');
    await pool.end();
    process.exit(0);
});

process.on('SIGINT', async () => {
    console.log('SIGINT signal received: closing HTTP server');
    await pool.end();
    process.exit(0);
});

module.exports = app;
