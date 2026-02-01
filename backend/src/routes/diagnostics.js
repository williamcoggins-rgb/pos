const express = require('express');
const router = express.Router();

// Diagnostic endpoint to check Stripe configuration
router.get('/stripe-check', async (req, res) => {
    const diagnostics = {
        timestamp: new Date().toISOString(),
        checks: []
    };

    // Check 1: Is Stripe Secret Key configured?
    const hasStripeKey = !!process.env.STRIPE_SECRET_KEY;
    diagnostics.checks.push({
        name: 'Stripe Secret Key Configured',
        status: hasStripeKey ? 'PASS' : 'FAIL',
        message: hasStripeKey
            ? `Key present (starts with: ${process.env.STRIPE_SECRET_KEY?.substring(0, 7)}...)`
            : 'STRIPE_SECRET_KEY environment variable is not set'
    });

    // Check 2: Is it a test key or live key?
    if (hasStripeKey) {
        const isTestKey = process.env.STRIPE_SECRET_KEY.startsWith('sk_test_');
        const isLiveKey = process.env.STRIPE_SECRET_KEY.startsWith('sk_live_');

        diagnostics.checks.push({
            name: 'Stripe Key Type',
            status: isTestKey ? 'PASS' : (isLiveKey ? 'WARNING' : 'FAIL'),
            message: isTestKey
                ? 'Using test mode key (correct for development)'
                : isLiveKey
                    ? 'Using LIVE mode key (use test keys for development!)'
                    : 'Key format not recognized - should start with sk_test_ or sk_live_'
        });
    }

    // Check 3: Can we initialize Stripe?
    try {
        const Stripe = require('stripe');
        const stripe = Stripe(process.env.STRIPE_SECRET_KEY);

        diagnostics.checks.push({
            name: 'Stripe SDK Initialization',
            status: 'PASS',
            message: 'Stripe SDK initialized successfully'
        });

        // Check 4: Can we make an API call to Stripe?
        try {
            const balance = await stripe.balance.retrieve();
            diagnostics.checks.push({
                name: 'Stripe API Connection',
                status: 'PASS',
                message: `Successfully connected to Stripe API. Account balance: ${JSON.stringify(balance.available)}`
            });
        } catch (apiError) {
            diagnostics.checks.push({
                name: 'Stripe API Connection',
                status: 'FAIL',
                message: `Failed to connect to Stripe: ${apiError.message}`,
                error_type: apiError.type,
                error_code: apiError.code
            });
        }

        // Check 5: Can we create Stripe Connect accounts?
        try {
            console.log('Testing Stripe Connect account creation...');
            console.log('Stripe API Version:', stripe.VERSION || 'default');

            // Try to create a test account to verify Connect is enabled
            const testAccount = await stripe.accounts.create({
                type: 'express',
                country: 'US',
                email: 'test-' + Date.now() + '@example.com',
                capabilities: {
                    card_payments: { requested: true },
                    transfers: { requested: true }
                },
                business_type: 'individual'
            });

            console.log('Test account created successfully:', testAccount.id);

            // If successful, delete the test account
            await stripe.accounts.del(testAccount.id);
            console.log('Test account deleted');

            diagnostics.checks.push({
                name: 'Stripe Connect Enabled',
                status: 'PASS',
                message: `Successfully created and deleted test Connect account. Stripe Connect is enabled! API Version: ${stripe.VERSION || 'default'}`
            });
        } catch (connectError) {
            console.error('Connect test failed:', connectError.message);
            console.error('Error type:', connectError.type);
            console.error('Error code:', connectError.code);

            let fixMessage = 'Go to https://dashboard.stripe.com/test/connect/accounts/overview and enable Connect';

            // Provide more specific fix instructions based on error message
            if (connectError.message && connectError.message.includes('platform-profile')) {
                fixMessage = `
                    <strong>Steps to fix:</strong><br>
                    1. Make sure you're in <strong>TEST MODE</strong> (toggle at top right of Stripe dashboard)<br>
                    2. Go to: <a href="https://dashboard.stripe.com/settings/connect/platform-profile" target="_blank" style="color: #00ff00;">Platform Profile Settings</a><br>
                    3. Fill out ALL required fields:<br>
                    &nbsp;&nbsp;&nbsp;- Business website (can use a placeholder like https://example.com)<br>
                    &nbsp;&nbsp;&nbsp;- Customer support info<br>
                    &nbsp;&nbsp;&nbsp;- Platform description<br>
                    &nbsp;&nbsp;&nbsp;- Loss liability settings<br>
                    4. <strong>Scroll to the bottom and click SAVE</strong><br>
                    5. Then refresh this diagnostic page<br>
                    <br>
                    <strong>Important:</strong> All fields must be filled out, even for test mode!
                `;
            } else if (connectError.message && connectError.message.includes('signed up for Connect')) {
                fixMessage = `
                    <strong>Complete These Steps:</strong><br>
                    1. <a href="https://dashboard.stripe.com/settings/connect/platform-profile" target="_blank" style="color: #00ff00;">Platform Profile</a> - Fill out completely<br>
                    2. <a href="https://dashboard.stripe.com/settings/connect" target="_blank" style="color: #00ff00;">Connect Branding</a> - Add business name, icon, and brand color<br>
                    3. <a href="https://dashboard.stripe.com/settings/connect/express" target="_blank" style="color: #00ff00;">Express Settings</a> - Check default capabilities and enable onboarding for US<br>
                    4. Refresh this page after completing all steps
                `;
            } else if (connectError.message && connectError.message.includes('client application')) {
                fixMessage = `
                    <strong>Branding Settings Required:</strong><br>
                    Go to: <a href="https://dashboard.stripe.com/settings/connect" target="_blank" style="color: #00ff00;">Connect Settings → Branding</a><br>
                    You MUST set:<br>
                    &nbsp;&nbsp;&nbsp;✓ Business name<br>
                    &nbsp;&nbsp;&nbsp;✓ Icon (upload a square logo)<br>
                    &nbsp;&nbsp;&nbsp;✓ Brand color<br>
                    <br>
                    Then refresh this page.
                `;
            }

            diagnostics.checks.push({
                name: 'Stripe Connect Enabled',
                status: 'FAIL',
                message: `Stripe Connect setup incomplete: ${connectError.message}`,
                error_type: connectError.type,
                error_code: connectError.code,
                fix: fixMessage
            });
        }

    } catch (error) {
        diagnostics.checks.push({
            name: 'Stripe SDK Initialization',
            status: 'FAIL',
            message: `Failed to initialize Stripe: ${error.message}`
        });
    }

    // Check 6: Database connectivity
    try {
        const { query } = require('../config/database');
        const result = await query('SELECT COUNT(*) as count FROM users');
        diagnostics.checks.push({
            name: 'Database Connection',
            status: 'PASS',
            message: `Database connected. ${result.rows[0].count} users in database.`
        });
    } catch (dbError) {
        diagnostics.checks.push({
            name: 'Database Connection',
            status: 'FAIL',
            message: `Database error: ${dbError.message}`
        });
    }

    // Overall status
    const failedChecks = diagnostics.checks.filter(c => c.status === 'FAIL').length;
    const warningChecks = diagnostics.checks.filter(c => c.status === 'WARNING').length;

    diagnostics.overall_status = failedChecks > 0 ? 'FAILED' : (warningChecks > 0 ? 'WARNING' : 'PASSED');
    diagnostics.summary = `${diagnostics.checks.length} checks run, ${failedChecks} failed, ${warningChecks} warnings`;

    // Return HTML for easy viewing
    res.send(`
<!DOCTYPE html>
<html>
<head>
    <title>Stripe Diagnostics</title>
    <style>
        body {
            font-family: monospace;
            background: #1a1a1a;
            color: #00ff00;
            padding: 20px;
            margin: 0;
        }
        .container {
            max-width: 900px;
            margin: 0 auto;
            background: #000;
            padding: 30px;
            border: 2px solid #00ff00;
            border-radius: 8px;
        }
        h1 {
            color: #00ff00;
            border-bottom: 2px solid #00ff00;
            padding-bottom: 10px;
        }
        .check {
            margin: 20px 0;
            padding: 15px;
            border-left: 4px solid #666;
            background: #0a0a0a;
        }
        .check.PASS { border-left-color: #00ff00; }
        .check.FAIL { border-left-color: #ff0000; color: #ff6666; }
        .check.WARNING { border-left-color: #ffaa00; color: #ffcc66; }
        .status {
            font-weight: bold;
            padding: 4px 12px;
            border-radius: 4px;
            display: inline-block;
            margin-bottom: 8px;
        }
        .status.PASS { background: #00ff00; color: #000; }
        .status.FAIL { background: #ff0000; color: #fff; }
        .status.WARNING { background: #ffaa00; color: #000; }
        .overall {
            font-size: 18px;
            padding: 20px;
            margin: 20px 0;
            text-align: center;
            border: 2px solid;
            border-radius: 8px;
        }
        .overall.PASSED { background: #003300; border-color: #00ff00; }
        .overall.FAILED { background: #330000; border-color: #ff0000; }
        .overall.WARNING { background: #332200; border-color: #ffaa00; }
        pre {
            background: #0a0a0a;
            padding: 10px;
            overflow-x: auto;
            border-radius: 4px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔧 BarberScore POS - Stripe Diagnostics</h1>
        <p>Timestamp: ${diagnostics.timestamp}</p>

        <div class="overall ${diagnostics.overall_status}">
            <strong>Overall Status: ${diagnostics.overall_status}</strong><br>
            ${diagnostics.summary}
        </div>

        ${diagnostics.checks.map(check => `
            <div class="check ${check.status}">
                <div class="status ${check.status}">${check.status}</div>
                <strong>${check.name}</strong><br>
                <div style="margin-top: 8px;">${check.message}</div>
                ${check.error_type ? `<div style="margin-top: 4px; opacity: 0.7;">Error Type: ${check.error_type}</div>` : ''}
                ${check.error_code ? `<div style="opacity: 0.7;">Error Code: ${check.error_code}</div>` : ''}
                ${check.fix ? `
                    <div style="margin-top: 12px; padding: 12px; background: rgba(255,255,255,0.1); border-radius: 4px;">
                        <strong style="color: #00ff00;">🔧 How to Fix:</strong><br>
                        <div style="margin-top: 6px;">${check.fix}</div>
                    </div>
                ` : ''}
            </div>
        `).join('')}

        <h2 style="margin-top: 40px;">Raw Data</h2>
        <pre>${JSON.stringify(diagnostics, null, 2)}</pre>
    </div>
</body>
</html>
    `);
});

module.exports = router;
