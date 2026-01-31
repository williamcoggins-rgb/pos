const express = require('express');
const bcrypt = require('bcrypt');
const jwt = require('jsonwebtoken');
const Stripe = require('stripe');
const { query, transaction } = require('../config/database');
const { authenticate } = require('../middleware/auth');
const { sendStripeOnboardingEmail, sendWelcomeEmail } = require('../services/email');

const router = express.Router();

// Initialize Stripe
let stripe;
if (process.env.STRIPE_SECRET_KEY) {
    stripe = Stripe(process.env.STRIPE_SECRET_KEY);
}

// ============================================
// REGISTER (Create new shop owner + shop)
// ============================================

router.post('/register', async (req, res, next) => {
    try {
        const {
            email,
            password,
            shopName,
            ownerName,
            phone
        } = req.body;

        // Validation
        if (!email || !password || !shopName || !ownerName) {
            return res.status(400).json({
                error: 'Bad Request',
                message: 'Email, password, shop name, and owner name are required'
            });
        }

        // Check if email already exists
        const existingUser = await query(
            'SELECT id FROM users WHERE email = $1',
            [email]
        );

        if (existingUser.rows.length > 0) {
            return res.status(409).json({
                error: 'Conflict',
                message: 'Email already registered'
            });
        }

        // Hash password
        const passwordHash = await bcrypt.hash(password, 10);

        // Create shop and user in a transaction
        const result = await transaction(async (client) => {
            // Create user first (without shop_id)
            const userResult = await client.query(
                `INSERT INTO users (email, password_hash, role, is_active)
                 VALUES ($1, $2, 'owner', true)
                 RETURNING id, email, role`,
                [email, passwordHash]
            );
            const user = userResult.rows[0];

            // Create shop
            const shopResult = await client.query(
                `INSERT INTO shops (name, owner_id, phone, email, is_active)
                 VALUES ($1, $2, $3, $4, true)
                 RETURNING id, name, created_at`,
                [shopName, user.id, phone, email]
            );
            const shop = shopResult.rows[0];

            // Update user with shop_id
            await client.query(
                'UPDATE users SET shop_id = $1 WHERE id = $2',
                [shop.id, user.id]
            );

            // Create default owner barber profile
            await client.query(
                `INSERT INTO barbers (user_id, shop_id, first_name, last_name, email, phone, is_active)
                 VALUES ($1, $2, $3, '', $4, $5, true)`,
                [user.id, shop.id, ownerName, email, phone]
            );

            return { user, shop };
        });

        // Generate JWT token
        const token = jwt.sign(
            { userId: result.user.id },
            process.env.JWT_SECRET,
            { expiresIn: process.env.JWT_EXPIRES_IN || '7d' }
        );

        // Send response immediately
        res.status(201).json({
            message: 'Registration successful',
            token,
            user: {
                id: result.user.id,
                email: result.user.email,
                role: result.user.role,
                shop: {
                    id: result.shop.id,
                    name: result.shop.name
                }
            }
        });

        // Async: Create Stripe account and send onboarding email (don't wait)
        if (stripe) {
            (async () => {
                try {
                    // Create Stripe Express account
                    const stripeAccount = await stripe.accounts.create({
                        type: 'express',
                        email: email,
                        capabilities: {
                            card_payments: { requested: true },
                            transfers: { requested: true }
                        },
                        business_type: 'individual',
                        metadata: {
                            user_id: result.user.id,
                            pos_system: 'barberscore'
                        }
                    });

                    // Save Stripe account ID to user
                    await query(
                        'UPDATE users SET stripe_account_id = $1 WHERE id = $2',
                        [stripeAccount.id, result.user.id]
                    );

                    // Create onboarding link
                    const BASE_URL = process.env.FRONTEND_URL || 'https://pos-ivrc.vercel.app';
                    const accountLink = await stripe.accountLinks.create({
                        account: stripeAccount.id,
                        refresh_url: `${BASE_URL}/stripe-refresh.html`,
                        return_url: `${BASE_URL}/stripe-success.html`,
                        type: 'account_onboarding'
                    });

                    // Send onboarding email
                    await sendStripeOnboardingEmail(email, accountLink.url, ownerName);

                    console.log(`✅ Stripe onboarding email sent to ${email}`);
                } catch (error) {
                    console.error('Error sending Stripe onboarding:', error);
                }
            })();
        }
    } catch (error) {
        next(error);
    }
});

// ============================================
// LOGIN
// ============================================

router.post('/login', async (req, res, next) => {
    try {
        const { email, password } = req.body;

        // Validation
        if (!email || !password) {
            return res.status(400).json({
                error: 'Bad Request',
                message: 'Email and password are required'
            });
        }

        // Get user with shop info
        const result = await query(
            `SELECT u.id, u.email, u.password_hash, u.role, u.shop_id, u.is_active,
                    s.name as shop_name
             FROM users u
             LEFT JOIN shops s ON u.shop_id = s.id
             WHERE u.email = $1`,
            [email]
        );

        if (result.rows.length === 0) {
            return res.status(401).json({
                error: 'Unauthorized',
                message: 'Invalid email or password'
            });
        }

        const user = result.rows[0];

        // Check if account is active
        if (!user.is_active) {
            return res.status(401).json({
                error: 'Unauthorized',
                message: 'Account is inactive'
            });
        }

        // Verify password
        const isPasswordValid = await bcrypt.compare(password, user.password_hash);

        if (!isPasswordValid) {
            return res.status(401).json({
                error: 'Unauthorized',
                message: 'Invalid email or password'
            });
        }

        // Update last login
        await query(
            'UPDATE users SET last_login = NOW() WHERE id = $1',
            [user.id]
        );

        // Generate JWT token
        const token = jwt.sign(
            { userId: user.id },
            process.env.JWT_SECRET,
            { expiresIn: process.env.JWT_EXPIRES_IN || '7d' }
        );

        res.json({
            message: 'Login successful',
            token,
            user: {
                id: user.id,
                email: user.email,
                role: user.role,
                shop: user.shop_id ? {
                    id: user.shop_id,
                    name: user.shop_name
                } : null
            }
        });
    } catch (error) {
        next(error);
    }
});

// ============================================
// GET CURRENT USER
// ============================================

router.get('/me', authenticate, async (req, res, next) => {
    try {
        const result = await query(
            `SELECT u.id, u.email, u.role, u.shop_id, u.created_at, u.last_login,
                    s.name as shop_name, s.address, s.phone, s.timezone
             FROM users u
             LEFT JOIN shops s ON u.shop_id = s.id
             WHERE u.id = $1`,
            [req.user.id]
        );

        if (result.rows.length === 0) {
            return res.status(404).json({
                error: 'Not Found',
                message: 'User not found'
            });
        }

        const user = result.rows[0];

        res.json({
            id: user.id,
            email: user.email,
            role: user.role,
            createdAt: user.created_at,
            lastLogin: user.last_login,
            shop: user.shop_id ? {
                id: user.shop_id,
                name: user.shop_name,
                address: user.address,
                phone: user.phone,
                timezone: user.timezone
            } : null
        });
    } catch (error) {
        next(error);
    }
});

// ============================================
// CHANGE PASSWORD
// ============================================

router.post('/change-password', authenticate, async (req, res, next) => {
    try {
        const { currentPassword, newPassword } = req.body;

        if (!currentPassword || !newPassword) {
            return res.status(400).json({
                error: 'Bad Request',
                message: 'Current password and new password are required'
            });
        }

        if (newPassword.length < 6) {
            return res.status(400).json({
                error: 'Bad Request',
                message: 'New password must be at least 6 characters'
            });
        }

        // Get current password hash
        const result = await query(
            'SELECT password_hash FROM users WHERE id = $1',
            [req.user.id]
        );

        const user = result.rows[0];

        // Verify current password
        const isPasswordValid = await bcrypt.compare(currentPassword, user.password_hash);

        if (!isPasswordValid) {
            return res.status(401).json({
                error: 'Unauthorized',
                message: 'Current password is incorrect'
            });
        }

        // Hash new password
        const newPasswordHash = await bcrypt.hash(newPassword, 10);

        // Update password
        await query(
            'UPDATE users SET password_hash = $1, updated_at = NOW() WHERE id = $2',
            [newPasswordHash, req.user.id]
        );

        res.json({
            message: 'Password changed successfully'
        });
    } catch (error) {
        next(error);
    }
});

module.exports = router;
