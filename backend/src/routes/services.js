const express = require('express');
const { query } = require('../config/database');
const { authenticate } = require('../middleware/auth');

const router = express.Router();

// All routes require authentication
router.use(authenticate);

// ============================================
// GET ALL SERVICES
// ============================================

router.get('/', async (req, res, next) => {
    try {
        const {
            shop_id,
            category,
            is_active
        } = req.query;

        let queryText = 'SELECT * FROM services WHERE 1=1';
        const params = [];
        let paramCount = 1;

        if (shop_id) {
            queryText += ` AND shop_id = $${paramCount++}`;
            params.push(shop_id);
        } else if (req.user.shop_id) {
            queryText += ` AND shop_id = $${paramCount++}`;
            params.push(req.user.shop_id);
        }

        if (category) {
            queryText += ` AND category = $${paramCount++}`;
            params.push(category);
        }

        if (is_active !== undefined) {
            queryText += ` AND is_active = $${paramCount++}`;
            params.push(is_active === 'true');
        }

        queryText += ' ORDER BY category, name';

        const result = await query(queryText, params);

        res.json({
            services: result.rows
        });
    } catch (error) {
        next(error);
    }
});

// ============================================
// GET SERVICE BY ID
// ============================================

router.get('/:id', async (req, res, next) => {
    try {
        const { id } = req.params;

        const result = await query(
            'SELECT * FROM services WHERE id = $1',
            [id]
        );

        if (result.rows.length === 0) {
            return res.status(404).json({
                error: 'Not Found',
                message: 'Service not found'
            });
        }

        res.json(result.rows[0]);
    } catch (error) {
        next(error);
    }
});

// ============================================
// CREATE SERVICE
// ============================================

router.post('/', async (req, res, next) => {
    try {
        const {
            shop_id,
            name,
            description,
            price,
            duration_minutes,
            category
        } = req.body;

        // Validation
        const shopIdToUse = shop_id || req.user.shop_id;
        if (!shopIdToUse || !name || price === undefined) {
            return res.status(400).json({
                error: 'Bad Request',
                message: 'Shop ID, name, and price are required'
            });
        }

        const result = await query(
            `INSERT INTO services (shop_id, name, description, price, duration_minutes, category, is_active)
             VALUES ($1, $2, $3, $4, $5, $6, true)
             RETURNING *`,
            [shopIdToUse, name, description, price, duration_minutes || 30, category]
        );

        res.status(201).json({
            message: 'Service created successfully',
            service: result.rows[0]
        });
    } catch (error) {
        next(error);
    }
});

// ============================================
// UPDATE SERVICE
// ============================================

router.patch('/:id', async (req, res, next) => {
    try {
        const { id } = req.params;
        const {
            name,
            description,
            price,
            duration_minutes,
            category,
            is_active
        } = req.body;

        const updates = [];
        const params = [id];
        let paramCount = 2;

        if (name !== undefined) {
            updates.push(`name = $${paramCount++}`);
            params.push(name);
        }
        if (description !== undefined) {
            updates.push(`description = $${paramCount++}`);
            params.push(description);
        }
        if (price !== undefined) {
            updates.push(`price = $${paramCount++}`);
            params.push(price);
        }
        if (duration_minutes !== undefined) {
            updates.push(`duration_minutes = $${paramCount++}`);
            params.push(duration_minutes);
        }
        if (category !== undefined) {
            updates.push(`category = $${paramCount++}`);
            params.push(category);
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
            `UPDATE services SET ${updates.join(', ')} WHERE id = $1 RETURNING *`,
            params
        );

        if (result.rows.length === 0) {
            return res.status(404).json({
                error: 'Not Found',
                message: 'Service not found'
            });
        }

        res.json({
            message: 'Service updated successfully',
            service: result.rows[0]
        });
    } catch (error) {
        next(error);
    }
});

// ============================================
// DELETE SERVICE
// ============================================

router.delete('/:id', async (req, res, next) => {
    try {
        const { id } = req.params;

        const result = await query(
            'DELETE FROM services WHERE id = $1 RETURNING *',
            [id]
        );

        if (result.rows.length === 0) {
            return res.status(404).json({
                error: 'Not Found',
                message: 'Service not found'
            });
        }

        res.json({
            message: 'Service deleted successfully'
        });
    } catch (error) {
        next(error);
    }
});

module.exports = router;
