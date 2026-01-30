const express = require('express');
const { query, transaction } = require('../config/database');
const { authenticate } = require('../middleware/auth');

const router = express.Router();

// All routes require authentication
router.use(authenticate);

// ============================================
// GET ALL PRODUCTS
// ============================================

router.get('/', async (req, res, next) => {
    try {
        const {
            shop_id,
            category,
            low_stock,
            is_active
        } = req.query;

        let queryText = 'SELECT * FROM products WHERE 1=1';
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

        if (low_stock === 'true') {
            queryText += ` AND quantity_in_stock <= reorder_level`;
        }

        if (is_active !== undefined) {
            queryText += ` AND is_active = $${paramCount++}`;
            params.push(is_active === 'true');
        }

        queryText += ' ORDER BY name';

        const result = await query(queryText, params);

        res.json({
            products: result.rows
        });
    } catch (error) {
        next(error);
    }
});

// ============================================
// GET PRODUCT BY ID
// ============================================

router.get('/:id', async (req, res, next) => {
    try {
        const { id } = req.params;

        const result = await query(
            'SELECT * FROM products WHERE id = $1',
            [id]
        );

        if (result.rows.length === 0) {
            return res.status(404).json({
                error: 'Not Found',
                message: 'Product not found'
            });
        }

        res.json(result.rows[0]);
    } catch (error) {
        next(error);
    }
});

// ============================================
// GET PRODUCT INVENTORY HISTORY
// ============================================

router.get('/:id/history', async (req, res, next) => {
    try {
        const { id } = req.params;
        const { limit = 50, offset = 0 } = req.query;

        const result = await query(
            `SELECT it.*, u.email as created_by_email
             FROM inventory_transactions it
             LEFT JOIN users u ON it.created_by = u.id
             WHERE it.product_id = $1
             ORDER BY it.created_at DESC
             LIMIT $2 OFFSET $3`,
            [id, limit, offset]
        );

        res.json({
            history: result.rows
        });
    } catch (error) {
        next(error);
    }
});

// ============================================
// CREATE PRODUCT
// ============================================

router.post('/', async (req, res, next) => {
    try {
        const {
            shop_id,
            name,
            description,
            sku,
            category,
            cost_price,
            retail_price,
            quantity_in_stock,
            reorder_level,
            reorder_quantity,
            supplier
        } = req.body;

        // Validation
        const shopIdToUse = shop_id || req.user.shop_id;
        if (!shopIdToUse || !name || retail_price === undefined) {
            return res.status(400).json({
                error: 'Bad Request',
                message: 'Shop ID, name, and retail price are required'
            });
        }

        const result = await query(
            `INSERT INTO products (
                shop_id, name, description, sku, category, cost_price, retail_price,
                quantity_in_stock, reorder_level, reorder_quantity, supplier, is_active
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, true)
            RETURNING *`,
            [
                shopIdToUse, name, description, sku, category, cost_price, retail_price,
                quantity_in_stock || 0, reorder_level || 5, reorder_quantity || 10, supplier
            ]
        );

        res.status(201).json({
            message: 'Product created successfully',
            product: result.rows[0]
        });
    } catch (error) {
        next(error);
    }
});

// ============================================
// UPDATE PRODUCT
// ============================================

router.patch('/:id', async (req, res, next) => {
    try {
        const { id } = req.params;
        const {
            name,
            description,
            sku,
            category,
            cost_price,
            retail_price,
            reorder_level,
            reorder_quantity,
            supplier,
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
        if (sku !== undefined) {
            updates.push(`sku = $${paramCount++}`);
            params.push(sku);
        }
        if (category !== undefined) {
            updates.push(`category = $${paramCount++}`);
            params.push(category);
        }
        if (cost_price !== undefined) {
            updates.push(`cost_price = $${paramCount++}`);
            params.push(cost_price);
        }
        if (retail_price !== undefined) {
            updates.push(`retail_price = $${paramCount++}`);
            params.push(retail_price);
        }
        if (reorder_level !== undefined) {
            updates.push(`reorder_level = $${paramCount++}`);
            params.push(reorder_level);
        }
        if (reorder_quantity !== undefined) {
            updates.push(`reorder_quantity = $${paramCount++}`);
            params.push(reorder_quantity);
        }
        if (supplier !== undefined) {
            updates.push(`supplier = $${paramCount++}`);
            params.push(supplier);
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
            `UPDATE products SET ${updates.join(', ')} WHERE id = $1 RETURNING *`,
            params
        );

        if (result.rows.length === 0) {
            return res.status(404).json({
                error: 'Not Found',
                message: 'Product not found'
            });
        }

        res.json({
            message: 'Product updated successfully',
            product: result.rows[0]
        });
    } catch (error) {
        next(error);
    }
});

// ============================================
// ADJUST INVENTORY
// ============================================

router.post('/:id/adjust', async (req, res, next) => {
    try {
        const { id } = req.params;
        const { quantity_change, transaction_type, notes } = req.body;

        if (quantity_change === undefined || !transaction_type) {
            return res.status(400).json({
                error: 'Bad Request',
                message: 'Quantity change and transaction type are required'
            });
        }

        const result = await transaction(async (client) => {
            // Get product
            const productResult = await client.query(
                'SELECT * FROM products WHERE id = $1',
                [id]
            );

            if (productResult.rows.length === 0) {
                throw new Error('Product not found');
            }

            const product = productResult.rows[0];

            // Update inventory
            const newQuantity = product.quantity_in_stock + quantity_change;

            if (newQuantity < 0) {
                throw new Error('Insufficient inventory');
            }

            await client.query(
                'UPDATE products SET quantity_in_stock = $1, updated_at = NOW() WHERE id = $2',
                [newQuantity, id]
            );

            // Create inventory transaction
            await client.query(
                `INSERT INTO inventory_transactions (
                    product_id, shop_id, transaction_type, quantity_change, notes, created_by
                ) VALUES ($1, $2, $3, $4, $5, $6)`,
                [id, product.shop_id, transaction_type, quantity_change, notes, req.user.id]
            );

            return { ...product, quantity_in_stock: newQuantity };
        });

        res.json({
            message: 'Inventory adjusted successfully',
            product: result
        });
    } catch (error) {
        next(error);
    }
});

// ============================================
// DELETE PRODUCT
// ============================================

router.delete('/:id', async (req, res, next) => {
    try {
        const { id } = req.params;

        const result = await query(
            'DELETE FROM products WHERE id = $1 RETURNING *',
            [id]
        );

        if (result.rows.length === 0) {
            return res.status(404).json({
                error: 'Not Found',
                message: 'Product not found'
            });
        }

        res.json({
            message: 'Product deleted successfully'
        });
    } catch (error) {
        next(error);
    }
});

module.exports = router;
