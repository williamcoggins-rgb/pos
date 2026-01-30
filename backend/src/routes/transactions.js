const express = require('express');
const { query, transaction } = require('../config/database');
const { authenticate, ensureSameShop } = require('../middleware/auth');

const router = express.Router();

// All routes require authentication
router.use(authenticate);

// ============================================
// GET ALL TRANSACTIONS
// ============================================

router.get('/', async (req, res, next) => {
    try {
        const {
            shop_id,
            customer_id,
            barber_id,
            payment_method,
            start_date,
            end_date,
            limit = 50,
            offset = 0
        } = req.query;

        let queryText = `
            SELECT t.*,
                   c.first_name as customer_first_name,
                   c.last_name as customer_last_name,
                   b.first_name as barber_first_name,
                   b.last_name as barber_last_name,
                   json_agg(
                       json_build_object(
                           'id', ti.id,
                           'name', ti.name,
                           'type', ti.item_type,
                           'quantity', ti.quantity,
                           'unit_price', ti.unit_price,
                           'total_price', ti.total_price
                       )
                   ) as items
            FROM transactions t
            LEFT JOIN customers c ON t.customer_id = c.id
            LEFT JOIN barbers b ON t.barber_id = b.id
            LEFT JOIN transaction_items ti ON t.id = ti.transaction_id
            WHERE 1=1
        `;
        const params = [];
        let paramCount = 1;

        if (shop_id) {
            queryText += ` AND t.shop_id = $${paramCount++}`;
            params.push(shop_id);
        } else if (req.user.shop_id) {
            queryText += ` AND t.shop_id = $${paramCount++}`;
            params.push(req.user.shop_id);
        }

        if (customer_id) {
            queryText += ` AND t.customer_id = $${paramCount++}`;
            params.push(customer_id);
        }

        if (barber_id) {
            queryText += ` AND t.barber_id = $${paramCount++}`;
            params.push(barber_id);
        }

        if (payment_method) {
            queryText += ` AND t.payment_method = $${paramCount++}`;
            params.push(payment_method);
        }

        if (start_date) {
            queryText += ` AND t.transaction_date >= $${paramCount++}`;
            params.push(start_date);
        }

        if (end_date) {
            queryText += ` AND t.transaction_date <= $${paramCount++}`;
            params.push(end_date);
        }

        queryText += `
            GROUP BY t.id, c.first_name, c.last_name, b.first_name, b.last_name
            ORDER BY t.transaction_date DESC
            LIMIT $${paramCount++} OFFSET $${paramCount}
        `;
        params.push(limit, offset);

        const result = await query(queryText, params);

        // Get total count
        let countQuery = 'SELECT COUNT(*) as total FROM transactions WHERE 1=1';
        const countParams = [];
        if (shop_id) {
            countQuery += ' AND shop_id = $1';
            countParams.push(shop_id);
        } else if (req.user.shop_id) {
            countQuery += ' AND shop_id = $1';
            countParams.push(req.user.shop_id);
        }

        const countResult = await query(countQuery, countParams);
        const total = parseInt(countResult.rows[0].total);

        res.json({
            transactions: result.rows,
            pagination: {
                total,
                limit: parseInt(limit),
                offset: parseInt(offset),
                hasMore: (parseInt(offset) + result.rows.length) < total
            }
        });
    } catch (error) {
        next(error);
    }
});

// ============================================
// GET TRANSACTION BY ID
// ============================================

router.get('/:id', async (req, res, next) => {
    try {
        const { id } = req.params;

        const result = await query(
            `SELECT t.*,
                    c.first_name as customer_first_name,
                    c.last_name as customer_last_name,
                    c.email as customer_email,
                    c.phone as customer_phone,
                    b.first_name as barber_first_name,
                    b.last_name as barber_last_name,
                    json_agg(
                        json_build_object(
                            'id', ti.id,
                            'name', ti.name,
                            'type', ti.item_type,
                            'quantity', ti.quantity,
                            'unit_price', ti.unit_price,
                            'total_price', ti.total_price
                        )
                    ) as items
             FROM transactions t
             LEFT JOIN customers c ON t.customer_id = c.id
             LEFT JOIN barbers b ON t.barber_id = b.id
             LEFT JOIN transaction_items ti ON t.id = ti.transaction_id
             WHERE t.id = $1
             GROUP BY t.id, c.first_name, c.last_name, c.email, c.phone, b.first_name, b.last_name`,
            [id]
        );

        if (result.rows.length === 0) {
            return res.status(404).json({
                error: 'Not Found',
                message: 'Transaction not found'
            });
        }

        res.json(result.rows[0]);
    } catch (error) {
        next(error);
    }
});

// ============================================
// CREATE TRANSACTION (Complete a sale)
// ============================================

router.post('/', async (req, res, next) => {
    try {
        const {
            shop_id,
            customer_id,
            barber_id,
            appointment_id,
            items,
            payment_method,
            tax,
            tip,
            discount,
            notes,
            client_rebooked,
            had_retail,
            had_addons
        } = req.body;

        // Validation
        if (!shop_id || !items || items.length === 0) {
            return res.status(400).json({
                error: 'Bad Request',
                message: 'Shop ID and at least one item are required'
            });
        }

        // Calculate totals
        const subtotal = items.reduce((sum, item) => sum + (item.unit_price * item.quantity), 0);
        const total = subtotal + (tax || 0) + (tip || 0) - (discount || 0);

        const result = await transaction(async (client) => {
            // Create transaction
            const transactionResult = await client.query(
                `INSERT INTO transactions (
                    shop_id, customer_id, barber_id, appointment_id,
                    subtotal, tax, tip, discount, total,
                    payment_method, payment_status, notes,
                    client_rebooked, had_retail, had_addons
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
                RETURNING *`,
                [
                    shop_id, customer_id, barber_id, appointment_id,
                    subtotal, tax || 0, tip || 0, discount || 0, total,
                    payment_method, 'completed', notes,
                    client_rebooked || false, had_retail || false, had_addons || false
                ]
            );

            const newTransaction = transactionResult.rows[0];

            // Create transaction items
            for (const item of items) {
                await client.query(
                    `INSERT INTO transaction_items (
                        transaction_id, service_id, product_id, item_type,
                        name, quantity, unit_price, total_price
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)`,
                    [
                        newTransaction.id,
                        item.service_id || null,
                        item.product_id || null,
                        item.type,
                        item.name,
                        item.quantity,
                        item.unit_price,
                        item.unit_price * item.quantity
                    ]
                );

                // If product, update inventory
                if (item.type === 'product' && item.product_id) {
                    await client.query(
                        'UPDATE products SET quantity_in_stock = quantity_in_stock - $1 WHERE id = $2',
                        [item.quantity, item.product_id]
                    );

                    // Create inventory transaction
                    await client.query(
                        `INSERT INTO inventory_transactions (
                            product_id, shop_id, transaction_type, quantity_change, notes
                        ) VALUES ($1, $2, 'sale', $3, $4)`,
                        [item.product_id, shop_id, -item.quantity, `Sold in transaction ${newTransaction.id}`]
                    );
                }
            }

            // Update customer stats if customer_id provided
            if (customer_id) {
                await client.query(
                    `UPDATE customers SET
                        lifetime_value = lifetime_value + $1,
                        visit_count = visit_count + 1,
                        last_visit_date = NOW(),
                        first_visit_date = COALESCE(first_visit_date, NOW())
                     WHERE id = $2`,
                    [total, customer_id]
                );
            }

            // Update appointment status if appointment_id provided
            if (appointment_id) {
                await client.query(
                    `UPDATE appointments SET status = 'completed' WHERE id = $1`,
                    [appointment_id]
                );
            }

            return newTransaction;
        });

        res.status(201).json({
            message: 'Transaction created successfully',
            transaction: result
        });
    } catch (error) {
        next(error);
    }
});

// ============================================
// UPDATE TRANSACTION
// ============================================

router.patch('/:id', async (req, res, next) => {
    try {
        const { id } = req.params;
        const {
            payment_status,
            notes,
            client_rebooked,
            had_retail,
            had_addons,
            is_no_show,
            is_cancelled
        } = req.body;

        const updates = [];
        const params = [id];
        let paramCount = 2;

        if (payment_status !== undefined) {
            updates.push(`payment_status = $${paramCount++}`);
            params.push(payment_status);
        }
        if (notes !== undefined) {
            updates.push(`notes = $${paramCount++}`);
            params.push(notes);
        }
        if (client_rebooked !== undefined) {
            updates.push(`client_rebooked = $${paramCount++}`);
            params.push(client_rebooked);
        }
        if (had_retail !== undefined) {
            updates.push(`had_retail = $${paramCount++}`);
            params.push(had_retail);
        }
        if (had_addons !== undefined) {
            updates.push(`had_addons = $${paramCount++}`);
            params.push(had_addons);
        }
        if (is_no_show !== undefined) {
            updates.push(`is_no_show = $${paramCount++}`);
            params.push(is_no_show);
        }
        if (is_cancelled !== undefined) {
            updates.push(`is_cancelled = $${paramCount++}`);
            params.push(is_cancelled);
        }

        if (updates.length === 0) {
            return res.status(400).json({
                error: 'Bad Request',
                message: 'No fields to update'
            });
        }

        updates.push('updated_at = NOW()');

        const result = await query(
            `UPDATE transactions SET ${updates.join(', ')} WHERE id = $1 RETURNING *`,
            params
        );

        if (result.rows.length === 0) {
            return res.status(404).json({
                error: 'Not Found',
                message: 'Transaction not found'
            });
        }

        res.json({
            message: 'Transaction updated successfully',
            transaction: result.rows[0]
        });
    } catch (error) {
        next(error);
    }
});

// ============================================
// DELETE TRANSACTION
// ============================================

router.delete('/:id', async (req, res, next) => {
    try {
        const { id } = req.params;

        const result = await query(
            'DELETE FROM transactions WHERE id = $1 RETURNING *',
            [id]
        );

        if (result.rows.length === 0) {
            return res.status(404).json({
                error: 'Not Found',
                message: 'Transaction not found'
            });
        }

        res.json({
            message: 'Transaction deleted successfully'
        });
    } catch (error) {
        next(error);
    }
});

module.exports = router;
