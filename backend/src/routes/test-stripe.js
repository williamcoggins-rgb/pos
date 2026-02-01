const express = require('express');
const router = express.Router();
const { authenticate } = require('../middleware/auth');
const { query } = require('../config/database');

// Initialize Stripe
const stripe = process.env.STRIPE_SECRET_KEY
    ? require('stripe')(process.env.STRIPE_SECRET_KEY)
    : null;

// Test creating a Stripe account for the logged-in user
router.get('/test-create-account', authenticate, async (req, res) => {
    const result = {
        timestamp: new Date().toISOString(),
        user_id: req.user.id,
        steps: []
    };

    try {
        // Step 1: Get user email
        result.steps.push({ step: 1, action: 'Fetching user email from database' });

        const userResult = await query('SELECT email, stripe_account_id FROM users WHERE id = $1', [req.user.id]);

        if (userResult.rows.length === 0) {
            result.steps.push({ step: 1, status: 'FAIL', error: 'User not found in database' });
            return res.status(404).json(result);
        }

        const user = userResult.rows[0];
        result.steps.push({
            step: 1,
            status: 'SUCCESS',
            email: user.email,
            existing_stripe_account_id: user.stripe_account_id
        });

        // Step 2: Check if Stripe is configured
        result.steps.push({ step: 2, action: 'Checking Stripe SDK' });

        if (!stripe) {
            result.steps.push({ step: 2, status: 'FAIL', error: 'Stripe SDK not initialized (no STRIPE_SECRET_KEY)' });
            return res.status(500).json(result);
        }

        result.steps.push({
            step: 2,
            status: 'SUCCESS',
            stripe_api_version: stripe.VERSION || 'default'
        });

        // Step 3: Try to create Stripe Express account
        result.steps.push({ step: 3, action: 'Creating Stripe Express account' });

        try {
            const account = await stripe.accounts.create({
                type: 'express',
                country: 'US',
                email: user.email,
                capabilities: {
                    card_payments: { requested: true },
                    transfers: { requested: true }
                },
                business_type: 'individual',
                metadata: {
                    user_id: req.user.id,
                    pos_system: 'barberscore',
                    test: 'true'
                }
            });

            result.steps.push({
                step: 3,
                status: 'SUCCESS',
                stripe_account_id: account.id,
                account_type: account.type,
                charges_enabled: account.charges_enabled,
                details_submitted: account.details_submitted
            });

            // Step 4: Try to create account link
            result.steps.push({ step: 4, action: 'Creating account onboarding link' });

            let BASE_URL = process.env.FRONTEND_URL || 'https://pos-ivrc.vercel.app';

            // Ensure URL has protocol
            if (!BASE_URL.startsWith('http://') && !BASE_URL.startsWith('https://')) {
                BASE_URL = `https://${BASE_URL}`;
            }

            // Remove trailing slash if present
            BASE_URL = BASE_URL.replace(/\/$/, '');

            const accountLink = await stripe.accountLinks.create({
                account: account.id,
                refresh_url: `${BASE_URL}/stripe-refresh.html`,
                return_url: `${BASE_URL}/stripe-success.html`,
                type: 'account_onboarding'
            });

            result.steps.push({
                step: 4,
                status: 'SUCCESS',
                onboarding_url: accountLink.url,
                expires_at: accountLink.expires_at
            });

            // Step 5: Clean up - delete test account
            result.steps.push({ step: 5, action: 'Cleaning up test account' });

            await stripe.accounts.del(account.id);

            result.steps.push({ step: 5, status: 'SUCCESS', message: 'Test account deleted' });

            result.overall_status = 'ALL TESTS PASSED';
            result.message = 'Stripe integration is working correctly!';

            return res.json(result);

        } catch (stripeError) {
            result.steps.push({
                step: result.steps[result.steps.length - 1].step,
                status: 'FAIL',
                error: {
                    message: stripeError.message,
                    type: stripeError.type,
                    code: stripeError.code,
                    param: stripeError.param,
                    statusCode: stripeError.statusCode,
                    raw: stripeError.raw
                }
            });

            result.overall_status = 'FAILED';
            return res.status(400).json(result);
        }

    } catch (error) {
        result.steps.push({
            status: 'FAIL',
            error: {
                message: error.message,
                stack: error.stack
            }
        });

        result.overall_status = 'ERROR';
        return res.status(500).json(result);
    }
});

module.exports = router;
