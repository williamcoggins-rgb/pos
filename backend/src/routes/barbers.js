const express = require('express');
const { query } = require('../config/database');
const { authenticate } = require('../middleware/auth');

const router = express.Router();

// All routes require authentication
router.use(authenticate);

// ============================================
// GET ALL BARBERS
// ============================================

router.get('/', async (req, res, next) => {
    try {
        const { shop_id, is_active } = req.query;

        let queryText = 'SELECT * FROM barbers WHERE 1=1';
        const params = [];
        let paramCount = 1;

        if (shop_id) {
            queryText += ` AND shop_id = $${paramCount++}`;
            params.push(shop_id);
        } else if (req.user.shop_id) {
            queryText += ` AND shop_id = $${paramCount++}`;
            params.push(req.user.shop_id);
        }

        if (is_active !== undefined) {
            queryText += ` AND is_active = $${paramCount++}`;
            params.push(is_active === 'true');
        }

        queryText += ' ORDER BY first_name, last_name';

        const result = await query(queryText, params);

        res.json({
            barbers: result.rows
        });
    } catch (error) {
        next(error);
    }
});

// ============================================
// GET BARBER BY ID
// ============================================

router.get('/:id', async (req, res, next) => {
    try {
        const { id } = req.params;

        const result = await query(
            'SELECT * FROM barbers WHERE id = $1',
            [id]
        );

        if (result.rows.length === 0) {
            return res.status(404).json({
                error: 'Not Found',
                message: 'Barber not found'
            });
        }

        res.json(result.rows[0]);
    } catch (error) {
        next(error);
    }
});

// ============================================
// GET BARBER PERFORMANCE
// ============================================

router.get('/:id/performance', async (req, res, next) => {
    try {
        const { id } = req.params;
        const { start_date, end_date } = req.query;

        let queryText = `
            SELECT
                COUNT(DISTINCT t.id) as total_transactions,
                COALESCE(SUM(t.total), 0) as total_revenue,
                COALESCE(AVG(t.total), 0) as avg_transaction_value,
                COUNT(DISTINCT t.customer_id) as unique_customers,
                COUNT(DISTINCT CASE WHEN t.client_rebooked THEN t.id END) as rebook_count,
                COUNT(DISTINCT CASE WHEN t.had_retail THEN t.id END) as retail_count,
                COUNT(DISTINCT CASE WHEN t.had_addons THEN t.id END) as addon_count,
                COALESCE(
                    COUNT(DISTINCT CASE WHEN t.client_rebooked THEN t.id END)::DECIMAL /
                    NULLIF(COUNT(DISTINCT t.id), 0) * 100,
                    0
                ) as rebook_rate
            FROM transactions t
            WHERE t.barber_id = $1 AND t.payment_status = 'completed'
        `;
        const params = [id];
        let paramCount = 2;

        if (start_date) {
            queryText += ` AND t.transaction_date >= $${paramCount++}`;
            params.push(start_date);
        }

        if (end_date) {
            queryText += ` AND t.transaction_date <= $${paramCount++}`;
            params.push(end_date);
        }

        const result = await query(queryText, params);

        res.json(result.rows[0]);
    } catch (error) {
        next(error);
    }
});

// ============================================
// CREATE BARBER
// ============================================

router.post('/', async (req, res, next) => {
    try {
        const {
            shop_id,
            user_id,
            first_name,
            last_name,
            email,
            phone,
            commission_rate,
            hourly_rate,
            hire_date,
            bio,
            specialties
        } = req.body;

        // Validation
        const shopIdToUse = shop_id || req.user.shop_id;
        if (!shopIdToUse || !first_name || !last_name) {
            return res.status(400).json({
                error: 'Bad Request',
                message: 'Shop ID, first name, and last name are required'
            });
        }

        const result = await query(
            `INSERT INTO barbers (
                shop_id, user_id, first_name, last_name, email, phone,
                commission_rate, hourly_rate, hire_date, bio, specialties, is_active
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, true)
            RETURNING *`,
            [
                shopIdToUse, user_id, first_name, last_name, email, phone,
                commission_rate || 0, hourly_rate, hire_date, bio,
                specialties ? JSON.stringify(specialties) : null
            ]
        );

        res.status(201).json({
            message: 'Barber created successfully',
            barber: result.rows[0]
        });
    } catch (error) {
        next(error);
    }
});

// ============================================
// UPDATE BARBER
// ============================================

router.patch('/:id', async (req, res, next) => {
    try {
        const { id } = req.params;
        const {
            first_name,
            last_name,
            email,
            phone,
            commission_rate,
            hourly_rate,
            hire_date,
            bio,
            specialties,
            is_active
        } = req.body;

        const updates = [];
        const params = [id];
        let paramCount = 2;

        if (first_name !== undefined) {
            updates.push(`first_name = $${paramCount++}`);
            params.push(first_name);
        }
        if (last_name !== undefined) {
            updates.push(`last_name = $${paramCount++}`);
            params.push(last_name);
        }
        if (email !== undefined) {
            updates.push(`email = $${paramCount++}`);
            params.push(email);
        }
        if (phone !== undefined) {
            updates.push(`phone = $${paramCount++}`);
            params.push(phone);
        }
        if (commission_rate !== undefined) {
            updates.push(`commission_rate = $${paramCount++}`);
            params.push(commission_rate);
        }
        if (hourly_rate !== undefined) {
            updates.push(`hourly_rate = $${paramCount++}`);
            params.push(hourly_rate);
        }
        if (hire_date !== undefined) {
            updates.push(`hire_date = $${paramCount++}`);
            params.push(hire_date);
        }
        if (bio !== undefined) {
            updates.push(`bio = $${paramCount++}`);
            params.push(bio);
        }
        if (specialties !== undefined) {
            updates.push(`specialties = $${paramCount++}`);
            params.push(JSON.stringify(specialties));
        }
        if (is_active !== undefined) {
            updates.push(`is_active = $${paramCount++}`);
            params.push(is_active);
        }

        if (updates.length === 0) {
            return res.status(400).json({
                error: 'Bad Request',
                message: 'No fields to update'
            });
        }

        updates.push('updated_at = NOW()');

        const result = await query(
            `UPDATE barbers SET ${updates.join(', ')} WHERE id = $1 RETURNING *`,
            params
        );

        if (result.rows.length === 0) {
            return res.status(404).json({
                error: 'Not Found',
                message: 'Barber not found'
            });
        }

        res.json({
            message: 'Barber updated successfully',
            barber: result.rows[0]
        });
    } catch (error) {
        next(error);
    }
});

// ============================================
// DELETE BARBER
// ============================================

router.delete('/:id', async (req, res, next) => {
    try {
        const { id } = req.params;

        const result = await query(
            'DELETE FROM barbers WHERE id = $1 RETURNING *',
            [id]
        );

        if (result.rows.length === 0) {
            return res.status(404).json({
                error: 'Not Found',
                message: 'Barber not found'
            });
        }

        res.json({
            message: 'Barber deleted successfully'
        });
    } catch (error) {
        next(error);
    }
});

module.exports = router;
