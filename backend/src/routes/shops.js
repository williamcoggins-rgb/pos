const express = require('express');
const { query } = require('../config/database');
const { authenticate, authorize } = require('../middleware/auth');

const router = express.Router();

// All routes require authentication
router.use(authenticate);

// ============================================
// GET ALL SHOPS (Admin only)
// ============================================

router.get('/', authorize('admin'), async (req, res, next) => {
    try {
        const result = await query(
            `SELECT s.*, u.email as owner_email
             FROM shops s
             LEFT JOIN users u ON s.owner_id = u.id
             ORDER BY s.name`
        );

        res.json({
            shops: result.rows
        });
    } catch (error) {
        next(error);
    }
});

// ============================================
// GET SHOP BY ID
// ============================================

router.get('/:id', async (req, res, next) => {
    try {
        const { id } = req.params;

        // Check if user has access to this shop
        if (req.user.role !== 'admin' && req.user.shop_id !== id) {
            return res.status(403).json({
                error: 'Forbidden',
                message: 'Access denied to this shop'
            });
        }

        const result = await query(
            `SELECT s.*, u.email as owner_email, u.id as owner_user_id
             FROM shops s
             LEFT JOIN users u ON s.owner_id = u.id
             WHERE s.id = $1`,
            [id]
        );

        if (result.rows.length === 0) {
            return res.status(404).json({
                error: 'Not Found',
                message: 'Shop not found'
            });
        }

        res.json(result.rows[0]);
    } catch (error) {
        next(error);
    }
});

// ============================================
// UPDATE SHOP
// ============================================

router.patch('/:id', async (req, res, next) => {
    try {
        const { id } = req.params;

        // Check if user has access to this shop
        if (req.user.role !== 'admin' && req.user.role !== 'owner') {
            return res.status(403).json({
                error: 'Forbidden',
                message: 'Only shop owners and admins can update shop settings'
            });
        }

        if (req.user.role === 'owner' && req.user.shop_id !== id) {
            return res.status(403).json({
                error: 'Forbidden',
                message: 'Access denied to this shop'
            });
        }

        const {
            name,
            address,
            phone,
            email,
            timezone,
            is_active
        } = req.body;

        const updates = [];
        const params = [id];
        let paramCount = 2;

        if (name !== undefined) {
            updates.push(`name = $${paramCount++}`);
            params.push(name);
        }
        if (address !== undefined) {
            updates.push(`address = $${paramCount++}`);
            params.push(address);
        }
        if (phone !== undefined) {
            updates.push(`phone = $${paramCount++}`);
            params.push(phone);
        }
        if (email !== undefined) {
            updates.push(`email = $${paramCount++}`);
            params.push(email);
        }
        if (timezone !== undefined) {
            updates.push(`timezone = $${paramCount++}`);
            params.push(timezone);
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
            `UPDATE shops SET ${updates.join(', ')} WHERE id = $1 RETURNING *`,
            params
        );

        if (result.rows.length === 0) {
            return res.status(404).json({
                error: 'Not Found',
                message: 'Shop not found'
            });
        }

        res.json({
            message: 'Shop updated successfully',
            shop: result.rows[0]
        });
    } catch (error) {
        next(error);
    }
});

// ============================================
// DELETE SHOP (Admin only)
// ============================================

router.delete('/:id', authorize('admin'), async (req, res, next) => {
    try {
        const { id } = req.params;

        const result = await query(
            'DELETE FROM shops WHERE id = $1 RETURNING *',
            [id]
        );

        if (result.rows.length === 0) {
            return res.status(404).json({
                error: 'Not Found',
                message: 'Shop not found'
            });
        }

        res.json({
            message: 'Shop deleted successfully'
        });
    } catch (error) {
        next(error);
    }
});

module.exports = router;
