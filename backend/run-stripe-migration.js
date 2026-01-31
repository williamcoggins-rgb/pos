const { Client } = require('pg');
const fs = require('fs');
const path = require('path');

const DATABASE_URL = process.argv[2];

if (!DATABASE_URL) {
    console.error('Usage: node run-stripe-migration.js <DATABASE_URL>');
    process.exit(1);
}

async function runMigration() {
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

        console.log('Reading migration file...');
        const migrationPath = path.join(__dirname, 'add-stripe-field.sql');
        const migration = fs.readFileSync(migrationPath, 'utf8');

        console.log('Running migration...');
        await client.query(migration);

        console.log('✅ Migration complete!');
        console.log('Added Stripe fields to users table:');
        console.log('  - stripe_account_id');
        console.log('  - stripe_onboarding_complete');
        console.log('  - stripe_charges_enabled');

    } catch (error) {
        console.error('❌ Migration error:', error.message);
        if (error.message.includes('already exists')) {
            console.log('✅ Fields already exist - migration not needed!');
        } else {
            process.exit(1);
        }
    } finally {
        await client.end();
    }
}

runMigration();
