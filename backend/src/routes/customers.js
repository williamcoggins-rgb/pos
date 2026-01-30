const express = require('express');
const { query } = require('../config/database');
const { authenticate } = require('../middleware/auth');

const router = express.Router();

// All routes require authentication
router.use(authenticate);

// ============================================
// GET ALL CUSTOMERS
// ============================================

router.get('/', async (req, res, next) => {
    try {
        const {
            shop_id,
            search,
            limit = 50,
            offset = 0
        } = req.query;

        let queryText = `
            SELECT c.*,
                   COUNT(DISTINCT t.id) as total_visits,
                   COALESCE(SUM(t.total), 0) as lifetime_value,
                   MAX(t.transaction_date) as last_visit_date,
                   b.first_name as preferred_barber_first_name,
                   b.last_name as preferred_barber_last_name
            FROM customers c
            LEFT JOIN transactions t ON c.id = t.customer_id AND t.payment_status = 'completed'
            LEFT JOIN barbers b ON c.preferred_barber_id = b.id
            WHERE 1=1
        `;
        const params = [];
        let paramCount = 1;

        // Filter by shop
        if (shop_id) {
            queryText += ` AND c.shop_id = $${paramCount++}`;
            params.push(shop_id);
        } else if (req.user.shop_id) {
            queryText += ` AND c.shop_id = $${paramCount++}`;
            params.push(req.user.shop_id);
        }

        // Search by name, email, or phone
        if (search) {
            queryText += ` AND (
                LOWER(c.first_name) LIKE LOWER($${paramCount}) OR
                LOWER(c.last_name) LIKE LOWER($${paramCount}) OR
                LOWER(c.email) LIKE LOWER($${paramCount}) OR
                c.phone LIKE $${paramCount}
            )`;
            params.push(`%${search}%`);
            paramCount++;
        }

        queryText += `
            GROUP BY c.id, b.first_name, b.last_name
            ORDER BY c.last_name, c.first_name
            LIMIT $${paramCount++} OFFSET $${paramCount}
        `;
        params.push(limit, offset);

        const result = await query(queryText, params);

        res.json({
            customers: result.rows,
            pagination: {
                limit: parseInt(limit),
                offset: parseInt(offset)
            }
        });
    } catch (error) {
        next(error);
    }
});

// ============================================
// GET CUSTOMER BY ID
// ============================================

router.get('/:id', async (req, res, next) => {
    try {
        const { id } = req.params;

        const result = await query(
            `SELECT c.*,
                    b.first_name as preferred_barber_first_name,
                    b.last_name as preferred_barber_last_name
             FROM customers c
             LEFT JOIN barbers b ON c.preferred_barber_id = b.id
             WHERE c.id = $1`,
            [id]
        );

        if (result.rows.length === 0) {
            return res.status(404).json({
                error: 'Not Found',
                message: 'Customer not found'
            });
        }

        res.json(result.rows[0]);
    } catch (error) {
        next(error);
    }
});

// ============================================
// CREATE CUSTOMER
// ============================================

router.post('/', async (req, res, next) => {
    try {
        const {
            shop_id,
            first_name,
            last_name,
            email,
            phone,
            notes,
            preferences,
            preferred_barber_id
        } = req.body;

        // Validation
        const shopIdToUse = shop_id || req.user.shop_id;
        if (!shopIdToUse) {
            return res.status(400).json({
                error: 'Bad Request',
                message: 'Shop ID is required'
            });
        }

        if (!email && !phone) {
            return res.status(400).json({
                error: 'Bad Request',
                message: 'Either email or phone is required'
            });
        }

        // Check for duplicate
        if (email) {
            const duplicate = await query(
                'SELECT id FROM customers WHERE shop_id = $1 AND email = $2',
                [shopIdToUse, email]
            );
            if (duplicate.rows.length > 0) {
                return res.status(409).json({
                    error: 'Conflict',
                    message: 'Customer with this email already exists'
                });
            }
        }

        const result = await query(
            `INSERT INTO customers (
                shop_id, first_name, last_name, email, phone, notes, preferences, preferred_barber_id
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING *`,
            [shopIdToUse, first_name, last_name, email, phone, notes, preferences ? JSON.stringify(preferences) : null, preferred_barber_id]
        );

        res.status(201).json({
            message: 'Customer created successfully',
            customer: result.rows[0]
        });
    } catch (error) {
        next(error);
    }
});

// ============================================
// UPDATE CUSTOMER
// ============================================

router.patch('/:id', async (req, res, next) => {
    try {
        const { id } = req.params;
        const {
            first_name,
            last_name,
            email,
            phone,
            notes,
            preferences,
            preferred_barber_id,
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
        if (notes !== undefined) {
            updates.push(`notes = $${paramCount++}`);
            params.push(notes);
        }
        if (preferences !== undefined) {
            updates.push(`preferences = $${paramCount++}`);
            params.push(JSON.stringify(preferences));
        }
        if (preferred_barber_id !== undefined) {
            updates.push(`preferred_barber_id = $${paramCount++}`);
            params.push(preferred_barber_id);
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
            `UPDATE customers SET ${updates.join(', ')} WHERE id = $1 RETURNING *`,
            params
        );

        if (result.rows.length === 0) {
            return res.status(404).json({
                error: 'Not Found',
                message: 'Customer not found'
            });
        }

        res.json({
            message: 'Customer updated successfully',
            customer: result.rows[0]
        });
    } catch (error) {
        next(error);
    }
});

// ============================================
// GET CUSTOMER TRANSACTION HISTORY
// ============================================

router.get('/:id/transactions', async (req, res, next) => {
    try {
        const { id } = req.params;
        const { limit = 20, offset = 0 } = req.query;

        const result = await query(
            `SELECT t.*,
                    b.first_name as barber_first_name,
                    b.last_name as barber_last_name,
                    json_agg(
                        json_build_object(
                            'name', ti.name,
                            'type', ti.item_type,
                            'quantity', ti.quantity,
                            'unit_price', ti.unit_price
                        )
                    ) as items
             FROM transactions t
             LEFT JOIN barbers b ON t.barber_id = b.id
             LEFT JOIN transaction_items ti ON t.id = ti.transaction_id
             WHERE t.customer_id = $1
             GROUP BY t.id, b.first_name, b.last_name
             ORDER BY t.transaction_date DESC
             LIMIT $2 OFFSET $3`,
            [id, limit, offset]
        );

        res.json({
            transactions: result.rows
        });
    } catch (error) {
        next(error);
    }
});

// ============================================
// DELETE CUSTOMER
// ============================================

router.delete('/:id', async (req, res, next) => {
    try {
        const { id } = req.params;

        const result = await query(
            'DELETE FROM customers WHERE id = $1 RETURNING *',
            [id]
        );

        if (result.rows.length === 0) {
            return res.status(404).json({
                error: 'Not Found',
                message: 'Customer not found'
            });
        }

        res.json({
            message: 'Customer deleted successfully'
        });
    } catch (error) {
        next(error);
    }
});

module.exports = router;
