const { Client } = require('pg');
const fs = require('fs');
const path = require('path');

const DATABASE_URL = process.argv[2];

if (!DATABASE_URL) {
    console.error('Usage: node setup-db.js <DATABASE_URL>');
    process.exit(1);
}

async function setupDatabase() {
    const client = new Client({
        connectionString: DATABASE_URL,
        ssl: {
            rejectUnauthorized: false
        }
    });

    try {
        console.log('Connecting to database...');
        await client.connect();
        console.log('Connected successfully!');

        console.log('Reading schema file...');
        const schemaPath = path.join(__dirname, 'schema.sql');
        const schema = fs.readFileSync(schemaPath, 'utf8');

        console.log('Executing schema...');
        await client.query(schema);

        console.log('✅ Database setup complete!');
        console.log('Created tables:');
        console.log('  - users, shops');
        console.log('  - customers, barbers');
        console.log('  - services, appointments');
        console.log('  - transactions, transaction_items');
        console.log('  - products, inventory_transactions');
        console.log('  - barberscore_metrics, audit_logs');
        console.log('  - Plus views and triggers');

    } catch (error) {
        console.error('❌ Error setting up database:', error.message);
        process.exit(1);
    } finally {
        await client.end();
    }
}

setupDatabase();
