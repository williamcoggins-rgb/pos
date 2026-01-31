const express = require('express');
const Stripe = require('stripe');
const { query } = require('../config/database');
const { authenticate } = require('../middleware/auth');
const { sendStripeOnboardingEmail } = require('../services/email');

const router = express.Router();

// Initialize Stripe
let stripe;
if (process.env.STRIPE_SECRET_KEY) {
    stripe = Stripe(process.env.STRIPE_SECRET_KEY);
}

// ============================================
// CREATE STRIPE CONNECT ACCOUNT
// ============================================
// Creates a Stripe Express account for an individual barber

router.post('/create-account', authenticate, async (req, res, next) => {
    try {
        if (!stripe) {
            return res.status(500).json({
                error: 'Stripe not configured',
                message: 'STRIPE_SECRET_KEY not set in environment variables'
            });
        }

        // Check if user already has a Stripe account
        if (req.user.stripe_account_id) {
            return res.status(400).json({
                error: 'Account Already Exists',
                message: 'You already have a Stripe account connected'
            });
        }

        // Get user email
        const userResult = await query(
            'SELECT email, role FROM users WHERE id = $1',
            [req.user.id]
        );

        if (userResult.rows.length === 0) {
            return res.status(404).json({ error: 'User not found' });
        }

        const userEmail = userResult.rows[0].email;

        // Create Stripe Express account
        const account = await stripe.accounts.create({
            type: 'express',
            country: 'US',  // Required by Stripe API
            email: userEmail,
            capabilities: {
                card_payments: { requested: true },
                transfers: { requested: true }
            },
            business_type: 'individual',
            metadata: {
                user_id: req.user.id,
                pos_system: 'barberscore'
            }
        });

        // Save Stripe account ID to user record
        await query(
            `UPDATE users
             SET stripe_account_id = $1,
                 updated_at = NOW()
             WHERE id = $2`,
            [account.id, req.user.id]
        );

        res.json({
            success: true,
            account_id: account.id,
            message: 'Stripe account created'
        });

    } catch (error) {
        console.error('Create Stripe account error:', error);
        next(error);
    }
});

// ============================================
// CREATE ACCOUNT LINK (ONBOARDING)
// ============================================
// Generates the onboarding link for user to complete Stripe setup

router.post('/create-account-link', authenticate, async (req, res, next) => {
    try {
        if (!stripe) {
            return res.status(500).json({
                error: 'Stripe not configured'
            });
        }

        // Get user's Stripe account ID
        let stripeAccountId = req.user.stripe_account_id;

        // If no account exists, create one first
        if (!stripeAccountId) {
            const userResult = await query(
                'SELECT email FROM users WHERE id = $1',
                [req.user.id]
            );

            const account = await stripe.accounts.create({
                type: 'express',
                country: 'US',  // Required by Stripe API
                email: userResult.rows[0].email,
                capabilities: {
                    card_payments: { requested: true },
                    transfers: { requested: true }
                },
                business_type: 'individual',
                metadata: {
                    user_id: req.user.id,
                    pos_system: 'barberscore'
                }
            });

            stripeAccountId = account.id;

            await query(
                'UPDATE users SET stripe_account_id = $1 WHERE id = $2',
                [stripeAccountId, req.user.id]
            );
        }

        // Create account link for onboarding
        const BASE_URL = process.env.FRONTEND_URL || 'https://pos-ivrc.vercel.app';

        const accountLink = await stripe.accountLinks.create({
            account: stripeAccountId,
            refresh_url: `${BASE_URL}/stripe-refresh.html`,
            return_url: `${BASE_URL}/stripe-success.html`,
            type: 'account_onboarding'
        });

        res.json({
            url: accountLink.url
        });

    } catch (error) {
        console.error('Create account link error:', error);
        next(error);
    }
});

// ============================================
// SEND ONBOARDING EMAIL
// ============================================
// Manually trigger sending the onboarding email

router.post('/send-onboarding-email', authenticate, async (req, res, next) => {
    try {
        if (!stripe) {
            return res.status(500).json({ error: 'Stripe not configured' });
        }

        // Get user info
        const userResult = await query(
            'SELECT email, stripe_account_id FROM users WHERE id = $1',
            [req.user.id]
        );

        if (userResult.rows.length === 0) {
            return res.status(404).json({ error: 'User not found' });
        }

        const user = userResult.rows[0];
        let stripeAccountId = user.stripe_account_id;

        // Create account if doesn't exist
        if (!stripeAccountId) {
            const account = await stripe.accounts.create({
                type: 'express',
                country: 'US',  // Required by Stripe API
                email: user.email,
                capabilities: {
                    card_payments: { requested: true },
                    transfers: { requested: true }
                },
                business_type: 'individual',
                metadata: {
                    user_id: req.user.id,
                    pos_system: 'barberscore'
                }
            });

            stripeAccountId = account.id;

            await query(
                'UPDATE users SET stripe_account_id = $1 WHERE id = $2',
                [stripeAccountId, req.user.id]
            );
        }

        // Create onboarding link
        const BASE_URL = process.env.FRONTEND_URL || 'https://pos-ivrc.vercel.app';

        const accountLink = await stripe.accountLinks.create({
            account: stripeAccountId,
            refresh_url: `${BASE_URL}/stripe-refresh.html`,
            return_url: `${BASE_URL}/stripe-success.html`,
            type: 'account_onboarding'
        });

        // Send email
        await sendStripeOnboardingEmail(
            user.email,
            accountLink.url,
            req.user.email.split('@')[0] // Use email prefix as name
        );

        res.json({
            success: true,
            message: 'Onboarding email sent'
        });

    } catch (error) {
        console.error('Send onboarding email error:', error);
        next(error);
    }
});

// ============================================
// CHECK ACCOUNT STATUS
// ============================================
// Check if Stripe account is fully set up

router.get('/account-status', authenticate, async (req, res, next) => {
    try {
        if (!stripe) {
            return res.status(500).json({ error: 'Stripe not configured' });
        }

        if (!req.user.stripe_account_id) {
            return res.json({
                has_account: false,
                onboarding_complete: false,
                charges_enabled: false
            });
        }

        // Get account details from Stripe
        const account = await stripe.accounts.retrieve(req.user.stripe_account_id);

        // Update local database
        await query(
            `UPDATE users
             SET stripe_onboarding_complete = $1,
                 stripe_charges_enabled = $2,
                 updated_at = NOW()
             WHERE id = $3`,
            [account.details_submitted, account.charges_enabled, req.user.id]
        );

        res.json({
            has_account: true,
            onboarding_complete: account.details_submitted,
            charges_enabled: account.charges_enabled,
            payouts_enabled: account.payouts_enabled,
            requirements: account.requirements
        });

    } catch (error) {
        console.error('Account status error:', error);
        next(error);
    }
});

// ============================================
// STRIPE WEBHOOK FOR ACCOUNT UPDATES
// ============================================
// Handle Stripe webhooks for account status changes
// TEMPORARILY DISABLED - express.raw() conflicts with express.json()
// TODO: Configure webhook endpoint separately

/*
router.post('/webhook', express.raw({ type: 'application/json' }), async (req, res) => {
    const sig = req.headers['stripe-signature'];
    const webhookSecret = process.env.STRIPE_CONNECT_WEBHOOK_SECRET;

    if (!webhookSecret) {
        return res.status(400).send('Webhook secret not configured');
    }

    let event;

    try {
        event = stripe.webhooks.constructEvent(req.body, sig, webhookSecret);
    } catch (err) {
        console.error('Webhook signature verification failed:', err.message);
        return res.status(400).send(`Webhook Error: ${err.message}`);
    }

    // Handle account update events
    try {
        switch (event.type) {
            case 'account.updated':
                const account = event.data.object;

                // Update user record
                await query(
                    `UPDATE users
                     SET stripe_onboarding_complete = $1,
                         stripe_charges_enabled = $2,
                         updated_at = NOW()
                     WHERE stripe_account_id = $3`,
                    [account.details_submitted, account.charges_enabled, account.id]
                );

                console.log('Account updated:', account.id);
                break;

            default:
                console.log(`Unhandled event type: ${event.type}`);
        }
    } catch (error) {
        console.error('Webhook processing error:', error);
        return res.status(500).send('Webhook processing failed');
    }

    res.json({ received: true });
});
*/

module.exports = router;
