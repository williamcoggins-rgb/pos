const express = require('express');
const Stripe = require('stripe');
const { query, transaction } = require('../config/database');
const { authenticate } = require('../middleware/auth');

const router = express.Router();

// Initialize Stripe (will be set with secret key from env)
let stripe;
if (process.env.STRIPE_SECRET_KEY) {
    stripe = Stripe(process.env.STRIPE_SECRET_KEY);
}

// All routes require authentication
router.use(authenticate);

// ============================================
// CREATE PAYMENT INTENT
// ============================================
// Creates a Stripe payment intent for processing a payment

router.post('/create-payment-intent', async (req, res, next) => {
    try {
        if (!stripe) {
            return res.status(500).json({
                error: 'Payment Processing Unavailable',
                message: 'Stripe is not configured. Please add STRIPE_SECRET_KEY to environment variables.'
            });
        }

        const { amount, currency = 'usd', customer_email, customer_name, metadata = {} } = req.body;

        if (!amount || amount <= 0) {
            return res.status(400).json({
                error: 'Bad Request',
                message: 'Amount must be greater than 0'
            });
        }

        // Create payment intent
        const paymentIntent = await stripe.paymentIntents.create({
            amount: Math.round(amount * 100), // Stripe uses cents
            currency: currency.toLowerCase(),
            automatic_payment_methods: {
                enabled: true,
            },
            receipt_email: customer_email || null,
            description: `BarberScore POS - ${req.user.shop_id}`,
            metadata: {
                shop_id: req.user.shop_id,
                user_id: req.user.id,
                customer_name: customer_name || 'Walk-in',
                ...metadata
            }
        });

        res.json({
            clientSecret: paymentIntent.client_secret,
            paymentIntentId: paymentIntent.id
        });

    } catch (error) {
        console.error('Stripe Payment Intent Error:', error);
        next(error);
    }
});

// ============================================
// CONFIRM PAYMENT & CREATE TRANSACTION
// ============================================
// After payment is confirmed, create transaction record in database

router.post('/confirm-payment', async (req, res, next) => {
    try {
        if (!stripe) {
            return res.status(500).json({
                error: 'Payment Processing Unavailable',
                message: 'Stripe is not configured.'
            });
        }

        const {
            payment_intent_id,
            transaction_data
        } = req.body;

        if (!payment_intent_id) {
            return res.status(400).json({
                error: 'Bad Request',
                message: 'payment_intent_id is required'
            });
        }

        // Verify payment intent with Stripe
        const paymentIntent = await stripe.paymentIntents.retrieve(payment_intent_id);

        if (paymentIntent.status !== 'succeeded') {
            return res.status(400).json({
                error: 'Payment Not Completed',
                message: `Payment status is: ${paymentIntent.status}`
            });
        }

        // Create transaction record in database
        const result = await transaction(async (client) => {
            const {
                shop_id,
                customer_id,
                barber_id,
                items,
                subtotal,
                tax = 0,
                tip = 0,
                discount = 0,
                total,
                client_rebooked = false,
                had_retail = false,
                had_addons = false,
                notes = ''
            } = transaction_data;

            // Insert transaction
            const transactionResult = await client.query(
                `INSERT INTO transactions (
                    shop_id, customer_id, barber_id, transaction_date,
                    subtotal, tax, tip, discount, total,
                    payment_method, payment_status,
                    client_rebooked, had_retail, had_addons, notes
                ) VALUES ($1, $2, $3, NOW(), $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                RETURNING *`,
                [
                    shop_id, customer_id, barber_id,
                    subtotal, tax, tip, discount, total,
                    'stripe_card', 'completed',
                    client_rebooked, had_retail, had_addons,
                    notes + ` (Stripe Payment: ${payment_intent_id})`
                ]
            );

            const transactionRecord = transactionResult.rows[0];

            // Insert transaction items
            if (items && items.length > 0) {
                for (const item of items) {
                    await client.query(
                        `INSERT INTO transaction_items (
                            transaction_id, service_id, product_id, item_type,
                            name, quantity, unit_price, total_price
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)`,
                        [
                            transactionRecord.id,
                            item.service_id || null,
                            item.product_id || null,
                            item.item_type || 'service',
                            item.name,
                            item.quantity || 1,
                            item.unit_price,
                            item.total_price || (item.unit_price * (item.quantity || 1))
                        ]
                    );

                    // Update product inventory if it's a product sale
                    if (item.item_type === 'product' && item.product_id) {
                        await client.query(
                            `UPDATE products
                             SET quantity_in_stock = quantity_in_stock - $1,
                                 updated_at = NOW()
                             WHERE id = $2`,
                            [item.quantity || 1, item.product_id]
                        );

                        // Log inventory transaction
                        await client.query(
                            `INSERT INTO inventory_transactions (
                                product_id, shop_id, transaction_type,
                                quantity_change, notes, created_by
                            ) VALUES ($1, $2, 'sale', $3, $4, $5)`,
                            [
                                item.product_id,
                                shop_id,
                                -(item.quantity || 1),
                                `Sale - Transaction ${transactionRecord.id}`,
                                req.user.id
                            ]
                        );
                    }
                }
            }

            // Update customer stats if customer_id provided
            if (customer_id) {
                await client.query(
                    `UPDATE customers
                     SET visit_count = visit_count + 1,
                         last_visit_date = NOW(),
                         lifetime_value = lifetime_value + $1,
                         updated_at = NOW()
                     WHERE id = $2`,
                    [total, customer_id]
                );
            }

            return transactionRecord;
        });

        res.json({
            success: true,
            transaction: result,
            payment_intent_id: payment_intent_id
        });

    } catch (error) {
        console.error('Confirm Payment Error:', error);
        next(error);
    }
});

// ============================================
// GET PAYMENT STATUS
// ============================================
// Check the status of a payment intent

router.get('/payment-status/:payment_intent_id', async (req, res, next) => {
    try {
        if (!stripe) {
            return res.status(500).json({
                error: 'Payment Processing Unavailable',
                message: 'Stripe is not configured.'
            });
        }

        const { payment_intent_id } = req.params;

        const paymentIntent = await stripe.paymentIntents.retrieve(payment_intent_id);

        res.json({
            id: paymentIntent.id,
            status: paymentIntent.status,
            amount: paymentIntent.amount / 100,
            currency: paymentIntent.currency,
            payment_method: paymentIntent.payment_method,
            created: paymentIntent.created
        });

    } catch (error) {
        console.error('Payment Status Error:', error);
        next(error);
    }
});

// ============================================
// REFUND PAYMENT
// ============================================
// Process a refund for a payment

router.post('/refund', async (req, res, next) => {
    try {
        if (!stripe) {
            return res.status(500).json({
                error: 'Payment Processing Unavailable',
                message: 'Stripe is not configured.'
            });
        }

        const { payment_intent_id, amount, reason = 'requested_by_customer' } = req.body;

        if (!payment_intent_id) {
            return res.status(400).json({
                error: 'Bad Request',
                message: 'payment_intent_id is required'
            });
        }

        // Create refund
        const refundData = {
            payment_intent: payment_intent_id,
            reason: reason
        };

        if (amount) {
            refundData.amount = Math.round(amount * 100); // Partial refund
        }

        const refund = await stripe.refunds.create(refundData);

        res.json({
            success: true,
            refund_id: refund.id,
            status: refund.status,
            amount: refund.amount / 100
        });

    } catch (error) {
        console.error('Refund Error:', error);
        next(error);
    }
});

// ============================================
// STRIPE WEBHOOK
// ============================================
// Handle Stripe webhook events (payment confirmations, failures, etc.)
// TEMPORARILY DISABLED - express.raw() conflicts with express.json()
// TODO: Configure webhook endpoint separately

/*
router.post('/webhook', express.raw({ type: 'application/json' }), async (req, res) => {
    const sig = req.headers['stripe-signature'];
    const webhookSecret = process.env.STRIPE_WEBHOOK_SECRET;

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

    // Handle the event
    switch (event.type) {
        case 'payment_intent.succeeded':
            const paymentIntent = event.data.object;
            console.log('Payment succeeded:', paymentIntent.id);
            // You could update transaction status here if needed
            break;

        case 'payment_intent.payment_failed':
            const failedPayment = event.data.object;
            console.log('Payment failed:', failedPayment.id);
            // Handle failed payment
            break;

        default:
            console.log(`Unhandled event type: ${event.type}`);
    }

    res.json({ received: true });
});
*/

module.exports = router;
