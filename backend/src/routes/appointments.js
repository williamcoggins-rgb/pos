const express = require('express');
const { query, transaction } = require('../config/database');
const { authenticate } = require('../middleware/auth');

const router = express.Router();

// All routes require authentication
router.use(authenticate);

// ============================================
// GET ALL APPOINTMENTS
// ============================================

router.get('/', async (req, res, next) => {
    try {
        const {
            shop_id,
            barber_id,
            customer_id,
            status,
            start_date,
            end_date
        } = req.query;

        let queryText = `
            SELECT a.*,
                   c.first_name as customer_first_name,
                   c.last_name as customer_last_name,
                   c.phone as customer_phone,
                   b.first_name as barber_first_name,
                   b.last_name as barber_last_name,
                   json_agg(
                       json_build_object(
                           'service_id', s.id,
                           'name', s.name,
                           'price', aps.price,
                           'duration', s.duration_minutes
                       )
                   ) as services
            FROM appointments a
            LEFT JOIN customers c ON a.customer_id = c.id
            LEFT JOIN barbers b ON a.barber_id = b.id
            LEFT JOIN appointment_services aps ON a.id = aps.appointment_id
            LEFT JOIN services s ON aps.service_id = s.id
            WHERE 1=1
        `;
        const params = [];
        let paramCount = 1;

        if (shop_id) {
            queryText += ` AND a.shop_id = $${paramCount++}`;
            params.push(shop_id);
        } else if (req.user.shop_id) {
            queryText += ` AND a.shop_id = $${paramCount++}`;
            params.push(req.user.shop_id);
        }

        if (barber_id) {
            queryText += ` AND a.barber_id = $${paramCount++}`;
            params.push(barber_id);
        }

        if (customer_id) {
            queryText += ` AND a.customer_id = $${paramCount++}`;
            params.push(customer_id);
        }

        if (status) {
            queryText += ` AND a.status = $${paramCount++}`;
            params.push(status);
        }

        if (start_date) {
            queryText += ` AND a.scheduled_start >= $${paramCount++}`;
            params.push(start_date);
        }

        if (end_date) {
            queryText += ` AND a.scheduled_start <= $${paramCount++}`;
            params.push(end_date);
        }

        queryText += `
            GROUP BY a.id, c.first_name, c.last_name, c.phone, b.first_name, b.last_name
            ORDER BY a.scheduled_start ASC
        `;

        const result = await query(queryText, params);

        res.json({
            appointments: result.rows
        });
    } catch (error) {
        next(error);
    }
});

// ============================================
// GET APPOINTMENT BY ID
// ============================================

router.get('/:id', async (req, res, next) => {
    try {
        const { id } = req.params;

        const result = await query(
            `SELECT a.*,
                    c.first_name as customer_first_name,
                    c.last_name as customer_last_name,
                    c.email as customer_email,
                    c.phone as customer_phone,
                    b.first_name as barber_first_name,
                    b.last_name as barber_last_name,
                    json_agg(
                        json_build_object(
                            'service_id', s.id,
                            'name', s.name,
                            'price', aps.price,
                            'duration', s.duration_minutes
                        )
                    ) as services
             FROM appointments a
             LEFT JOIN customers c ON a.customer_id = c.id
             LEFT JOIN barbers b ON a.barber_id = b.id
             LEFT JOIN appointment_services aps ON a.id = aps.appointment_id
             LEFT JOIN services s ON aps.service_id = s.id
             WHERE a.id = $1
             GROUP BY a.id, c.first_name, c.last_name, c.email, c.phone, b.first_name, b.last_name`,
            [id]
        );

        if (result.rows.length === 0) {
            return res.status(404).json({
                error: 'Not Found',
                message: 'Appointment not found'
            });
        }

        res.json(result.rows[0]);
    } catch (error) {
        next(error);
    }
});

// ============================================
// CREATE APPOINTMENT
// ============================================

router.post('/', async (req, res, next) => {
    try {
        const {
            shop_id,
            customer_id,
            barber_id,
            scheduled_start,
            scheduled_end,
            services,
            notes
        } = req.body;

        // Validation
        const shopIdToUse = shop_id || req.user.shop_id;
        if (!shopIdToUse || !scheduled_start || !scheduled_end) {
            return res.status(400).json({
                error: 'Bad Request',
                message: 'Shop ID, scheduled start, and scheduled end are required'
            });
        }

        const result = await transaction(async (client) => {
            // Create appointment
            const appointmentResult = await client.query(
                `INSERT INTO appointments (
                    shop_id, customer_id, barber_id, scheduled_start, scheduled_end, status, notes
                ) VALUES ($1, $2, $3, $4, $5, 'scheduled', $6)
                RETURNING *`,
                [shopIdToUse, customer_id, barber_id, scheduled_start, scheduled_end, notes]
            );

            const appointment = appointmentResult.rows[0];

            // Add services if provided
            if (services && services.length > 0) {
                for (const service of services) {
                    await client.query(
                        `INSERT INTO appointment_services (appointment_id, service_id, price)
                         VALUES ($1, $2, $3)`,
                        [appointment.id, service.service_id, service.price]
                    );
                }
            }

            return appointment;
        });

        res.status(201).json({
            message: 'Appointment created successfully',
            appointment: result
        });
    } catch (error) {
        next(error);
    }
});

// ============================================
// UPDATE APPOINTMENT
// ============================================

router.patch('/:id', async (req, res, next) => {
    try {
        const { id } = req.params;
        const {
            scheduled_start,
            scheduled_end,
            status,
            notes,
            reminder_sent
        } = req.body;

        const updates = [];
        const params = [id];
        let paramCount = 2;

        if (scheduled_start !== undefined) {
            updates.push(`scheduled_start = $${paramCount++}`);
            params.push(scheduled_start);
        }
        if (scheduled_end !== undefined) {
            updates.push(`scheduled_end = $${paramCount++}`);
            params.push(scheduled_end);
        }
        if (status !== undefined) {
            updates.push(`status = $${paramCount++}`);
            params.push(status);
        }
        if (notes !== undefined) {
            updates.push(`notes = $${paramCount++}`);
            params.push(notes);
        }
        if (reminder_sent !== undefined) {
            updates.push(`reminder_sent = $${paramCount++}`);
            params.push(reminder_sent);
        }

        if (updates.length === 0) {
            return res.status(400).json({
                error: 'Bad Request',
                message: 'No fields to update'
            });
        }

        updates.push('updated_at = NOW()');

        const result = await query(
            `UPDATE appointments SET ${updates.join(', ')} WHERE id = $1 RETURNING *`,
            params
        );

        if (result.rows.length === 0) {
            return res.status(404).json({
                error: 'Not Found',
                message: 'Appointment not found'
            });
        }

        res.json({
            message: 'Appointment updated successfully',
            appointment: result.rows[0]
        });
    } catch (error) {
        next(error);
    }
});

// ============================================
// DELETE APPOINTMENT
// ============================================

router.delete('/:id', async (req, res, next) => {
    try {
        const { id } = req.params;

        const result = await query(
            'DELETE FROM appointments WHERE id = $1 RETURNING *',
            [id]
        );

        if (result.rows.length === 0) {
            return res.status(404).json({
                error: 'Not Found',
                message: 'Appointment not found'
            });
        }

        res.json({
            message: 'Appointment deleted successfully'
        });
    } catch (error) {
        next(error);
    }
});

module.exports = router;
