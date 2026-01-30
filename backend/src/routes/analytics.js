const express = require('express');
const { query } = require('../config/database');
const { authenticate } = require('../middleware/auth');

const router = express.Router();

// All routes require authentication
router.use(authenticate);

// ============================================
// GET DASHBOARD SUMMARY
// ============================================

router.get('/dashboard', async (req, res, next) => {
    try {
        const { shop_id, start_date, end_date } = req.query;

        const shopIdToUse = shop_id || req.user.shop_id;

        let dateFilter = '';
        const params = [shopIdToUse];
        let paramCount = 2;

        if (start_date) {
            dateFilter += ` AND transaction_date >= $${paramCount++}`;
            params.push(start_date);
        }
        if (end_date) {
            dateFilter += ` AND transaction_date <= $${paramCount++}`;
            params.push(end_date);
        }

        const result = await query(
            `SELECT
                COUNT(DISTINCT id) as total_transactions,
                COUNT(DISTINCT customer_id) as unique_customers,
                COALESCE(SUM(total), 0) as total_revenue,
                COALESCE(SUM(tax), 0) as total_tax,
                COALESCE(SUM(tip), 0) as total_tips,
                COALESCE(AVG(total), 0) as avg_transaction_value,
                COUNT(DISTINCT CASE WHEN client_rebooked THEN id END) as rebook_count,
                COUNT(DISTINCT CASE WHEN had_retail THEN id END) as retail_count,
                COUNT(DISTINCT CASE WHEN had_addons THEN id END) as addon_count,
                COUNT(DISTINCT CASE WHEN is_no_show THEN id END) as no_show_count,
                COUNT(DISTINCT CASE WHEN is_cancelled THEN id END) as cancelled_count,
                COALESCE(
                    COUNT(DISTINCT CASE WHEN client_rebooked THEN id END)::DECIMAL /
                    NULLIF(COUNT(DISTINCT id), 0) * 100,
                    0
                ) as rebook_rate,
                COALESCE(
                    (COUNT(DISTINCT id) - COUNT(DISTINCT CASE WHEN is_no_show OR is_cancelled THEN id END))::DECIMAL /
                    NULLIF(COUNT(DISTINCT id), 0) * 100,
                    100
                ) as completion_rate
             FROM transactions
             WHERE shop_id = $1 AND payment_status = 'completed' ${dateFilter}`,
            params
        );

        res.json(result.rows[0]);
    } catch (error) {
        next(error);
    }
});

// ============================================
// GET SALES BY PERIOD (Daily, Weekly, Monthly)
// ============================================

router.get('/sales-by-period', async (req, res, next) => {
    try {
        const { shop_id, period = 'day', start_date, end_date } = req.query;

        const shopIdToUse = shop_id || req.user.shop_id;

        let periodTrunc = 'day';
        if (period === 'week') periodTrunc = 'week';
        if (period === 'month') periodTrunc = 'month';

        let dateFilter = '';
        const params = [shopIdToUse];
        let paramCount = 2;

        if (start_date) {
            dateFilter += ` AND transaction_date >= $${paramCount++}`;
            params.push(start_date);
        }
        if (end_date) {
            dateFilter += ` AND transaction_date <= $${paramCount++}`;
            params.push(end_date);
        }

        const result = await query(
            `SELECT
                DATE_TRUNC('${periodTrunc}', transaction_date) as period,
                COUNT(DISTINCT id) as transaction_count,
                COUNT(DISTINCT customer_id) as unique_customers,
                COALESCE(SUM(total), 0) as total_revenue,
                COALESCE(AVG(total), 0) as avg_transaction_value
             FROM transactions
             WHERE shop_id = $1 AND payment_status = 'completed' ${dateFilter}
             GROUP BY DATE_TRUNC('${periodTrunc}', transaction_date)
             ORDER BY period DESC`,
            params
        );

        res.json({
            sales: result.rows
        });
    } catch (error) {
        next(error);
    }
});

// ============================================
// GET TOP SERVICES
// ============================================

router.get('/top-services', async (req, res, next) => {
    try {
        const { shop_id, start_date, end_date, limit = 10 } = req.query;

        const shopIdToUse = shop_id || req.user.shop_id;

        let dateFilter = '';
        const params = [shopIdToUse];
        let paramCount = 2;

        if (start_date) {
            dateFilter += ` AND t.transaction_date >= $${paramCount++}`;
            params.push(start_date);
        }
        if (end_date) {
            dateFilter += ` AND t.transaction_date <= $${paramCount++}`;
            params.push(end_date);
        }

        params.push(limit);

        const result = await query(
            `SELECT
                ti.name,
                s.category,
                COUNT(ti.id) as times_sold,
                COALESCE(SUM(ti.total_price), 0) as total_revenue,
                COALESCE(AVG(ti.unit_price), 0) as avg_price
             FROM transaction_items ti
             JOIN transactions t ON ti.transaction_id = t.id
             LEFT JOIN services s ON ti.service_id = s.id
             WHERE t.shop_id = $1 AND ti.item_type = 'service' AND t.payment_status = 'completed' ${dateFilter}
             GROUP BY ti.name, s.category
             ORDER BY times_sold DESC
             LIMIT $${paramCount}`,
            params
        );

        res.json({
            services: result.rows
        });
    } catch (error) {
        next(error);
    }
});

// ============================================
// GET TOP CUSTOMERS
// ============================================

router.get('/top-customers', async (req, res, next) => {
    try {
        const { shop_id, limit = 10 } = req.query;

        const shopIdToUse = shop_id || req.user.shop_id;

        const result = await query(
            `SELECT
                c.id,
                c.first_name,
                c.last_name,
                c.email,
                c.phone,
                COUNT(DISTINCT t.id) as visit_count,
                COALESCE(SUM(t.total), 0) as lifetime_value,
                MAX(t.transaction_date) as last_visit
             FROM customers c
             JOIN transactions t ON c.id = t.customer_id
             WHERE c.shop_id = $1 AND t.payment_status = 'completed'
             GROUP BY c.id
             ORDER BY lifetime_value DESC
             LIMIT $2`,
            [shopIdToUse, limit]
        );

        res.json({
            customers: result.rows
        });
    } catch (error) {
        next(error);
    }
});

// ============================================
// GET BARBER LEADERBOARD
// ============================================

router.get('/barber-leaderboard', async (req, res, next) => {
    try {
        const { shop_id, start_date, end_date } = req.query;

        const shopIdToUse = shop_id || req.user.shop_id;

        let dateFilter = '';
        const params = [shopIdToUse];
        let paramCount = 2;

        if (start_date) {
            dateFilter += ` AND t.transaction_date >= $${paramCount++}`;
            params.push(start_date);
        }
        if (end_date) {
            dateFilter += ` AND t.transaction_date <= $${paramCount++}`;
            params.push(end_date);
        }

        const result = await query(
            `SELECT
                b.id,
                b.first_name,
                b.last_name,
                COUNT(DISTINCT t.id) as total_transactions,
                COALESCE(SUM(t.total), 0) as total_revenue,
                COALESCE(AVG(t.total), 0) as avg_transaction_value,
                COUNT(DISTINCT t.customer_id) as unique_customers,
                COALESCE(
                    COUNT(DISTINCT CASE WHEN t.client_rebooked THEN t.id END)::DECIMAL /
                    NULLIF(COUNT(DISTINCT t.id), 0) * 100,
                    0
                ) as rebook_rate
             FROM barbers b
             LEFT JOIN transactions t ON b.id = t.barber_id AND t.payment_status = 'completed' ${dateFilter.replace('t.transaction_date', 'transaction_date')}
             WHERE b.shop_id = $1 AND b.is_active = true
             GROUP BY b.id
             ORDER BY total_revenue DESC`,
            params
        );

        res.json({
            barbers: result.rows
        });
    } catch (error) {
        next(error);
    }
});

// ============================================
// GET PAYMENT METHOD BREAKDOWN
// ============================================

router.get('/payment-methods', async (req, res, next) => {
    try {
        const { shop_id, start_date, end_date } = req.query;

        const shopIdToUse = shop_id || req.user.shop_id;

        let dateFilter = '';
        const params = [shopIdToUse];
        let paramCount = 2;

        if (start_date) {
            dateFilter += ` AND transaction_date >= $${paramCount++}`;
            params.push(start_date);
        }
        if (end_date) {
            dateFilter += ` AND transaction_date <= $${paramCount++}`;
            params.push(end_date);
        }

        const result = await query(
            `SELECT
                COALESCE(payment_method, 'Not Specified') as payment_method,
                COUNT(id) as transaction_count,
                COALESCE(SUM(total), 0) as total_revenue,
                COALESCE(AVG(total), 0) as avg_transaction_value
             FROM transactions
             WHERE shop_id = $1 AND payment_status = 'completed' ${dateFilter}
             GROUP BY payment_method
             ORDER BY transaction_count DESC`,
            params
        );

        res.json({
            payment_methods: result.rows
        });
    } catch (error) {
        next(error);
    }
});

// ============================================
// CALCULATE BARBERSCORE
// ============================================

router.get('/barberscore', async (req, res, next) => {
    try {
        const { shop_id, barber_id } = req.query;

        const shopIdToUse = shop_id || req.user.shop_id;

        // Get all transactions for the shop/barber
        let queryText = `
            SELECT *
            FROM transactions
            WHERE shop_id = $1 AND payment_status = 'completed' AND is_cancelled = false
        `;
        const params = [shopIdToUse];

        if (barber_id) {
            queryText += ' AND barber_id = $2';
            params.push(barber_id);
        }

        queryText += ' ORDER BY transaction_date ASC';

        const transactionResult = await query(queryText, params);
        const transactions = transactionResult.rows;

        if (transactions.length === 0) {
            return res.json({
                score: 0,
                tier: 0,
                tier_name: 'Getting Started',
                metrics: {
                    total_transactions: 0,
                    days_active: 0,
                    rebook_rate: 0,
                    retail_rate: 0,
                    addon_rate: 0,
                    completion_rate: 100
                }
            });
        }

        // Calculate metrics (use your existing BarberScore algorithm from frontend)
        const validTransactions = transactions.filter(t => !t.is_no_show);
        const totalTransactions = validTransactions.length;

        const rebookCount = validTransactions.filter(t => t.client_rebooked).length;
        const retailCount = validTransactions.filter(t => t.had_retail).length;
        const addonCount = validTransactions.filter(t => t.had_addons).length;

        const rebookRate = totalTransactions > 0 ? (rebookCount / totalTransactions) * 100 : 0;
        const retailRate = totalTransactions > 0 ? (retailCount / totalTransactions) * 100 : 0;
        const addonRate = totalTransactions > 0 ? (addonCount / totalTransactions) * 100 : 0;
        const completionRate = transactions.length > 0 ?
            ((transactions.length - transactions.filter(t => t.is_no_show || t.is_cancelled).length) / transactions.length) * 100 : 100;

        // Calculate days active
        const uniqueDays = new Set(
            validTransactions.map(t => new Date(t.transaction_date).toDateString())
        ).size;

        const firstTransaction = new Date(transactions[0].transaction_date);
        const lastTransaction = new Date(transactions[transactions.length - 1].transaction_date);
        const daysActive = Math.floor((lastTransaction - firstTransaction) / (1000 * 60 * 60 * 24)) + 1;

        // Simple tier calculation (you can use your existing algorithm)
        let score = 0;
        let tier = 0;
        let tierName = 'Getting Started';

        // Time-based weight (simplified - use your full algorithm)
        let timeWeight = 0.05;
        if (daysActive >= 7 && daysActive < 30) timeWeight = 0.15;
        else if (daysActive >= 30 && daysActive < 90) timeWeight = 0.35;
        else if (daysActive >= 90 && daysActive < 180) timeWeight = 0.65;
        else if (daysActive >= 180) timeWeight = 1.0;

        // Calculate base score
        const rebookScore = rebookRate * 2;
        const completionScore = completionRate * 1.5;
        const retailScore = retailRate * 1.2;
        const addonScore = addonRate * 1;
        const consistencyScore = (uniqueDays / Math.max(daysActive, 1)) * 30;

        const baseScore = (rebookScore + completionScore + retailScore + addonScore + consistencyScore) * timeWeight;
        score = Math.round(Math.min(baseScore, 850));

        // Determine tier
        if (score >= 750) { tier = 5; tierName = 'Elite'; }
        else if (score >= 650) { tier = 4; tierName = 'Established'; }
        else if (score >= 550) { tier = 3; tierName = 'Growing'; }
        else if (score >= 450) { tier = 2; tierName = 'Building'; }
        else if (score >= 350) { tier = 1; tierName = 'Emerging'; }
        else { tier = 0; tierName = 'Getting Started'; }

        res.json({
            score,
            tier,
            tier_name: tierName,
            metrics: {
                total_transactions: totalTransactions,
                days_active: daysActive,
                unique_days_worked: uniqueDays,
                rebook_rate: rebookRate.toFixed(1),
                retail_rate: retailRate.toFixed(1),
                addon_rate: addonRate.toFixed(1),
                completion_rate: completionRate.toFixed(1),
                time_weight: timeWeight
            }
        });
    } catch (error) {
        next(error);
    }
});

module.exports = router;
