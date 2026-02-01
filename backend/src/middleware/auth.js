const jwt = require('jsonwebtoken');
const { query } = require('../config/database');

// Verify JWT token and attach user to request
const authenticate = async (req, res, next) => {
    try {
        // Get token from header
        const authHeader = req.headers.authorization;
        if (!authHeader || !authHeader.startsWith('Bearer ')) {
            return res.status(401).json({
                error: 'Unauthorized',
                message: 'No token provided'
            });
        }

        const token = authHeader.substring(7); // Remove 'Bearer ' prefix

        // Verify token
        const decoded = jwt.verify(token, process.env.JWT_SECRET);

        // Get user from database
        const result = await query(
            'SELECT id, email, role, shop_id, is_active, stripe_account_id, stripe_onboarding_complete, stripe_charges_enabled FROM users WHERE id = $1',
            [decoded.userId]
        );

        if (result.rows.length === 0) {
            return res.status(401).json({
                error: 'Unauthorized',
                message: 'User not found'
            });
        }

        const user = result.rows[0];

        if (!user.is_active) {
            return res.status(401).json({
                error: 'Unauthorized',
                message: 'User account is inactive'
            });
        }

        // Attach user to request
        req.user = user;
        next();
    } catch (error) {
        if (error.name === 'JsonWebTokenError') {
            return res.status(401).json({
                error: 'Unauthorized',
                message: 'Invalid token'
            });
        }
        if (error.name === 'TokenExpiredError') {
            return res.status(401).json({
                error: 'Unauthorized',
                message: 'Token expired'
            });
        }
        next(error);
    }
};

// Check if user has required role
const authorize = (...roles) => {
    return (req, res, next) => {
        if (!req.user) {
            return res.status(401).json({
                error: 'Unauthorized',
                message: 'Authentication required'
            });
        }

        if (!roles.includes(req.user.role)) {
            return res.status(403).json({
                error: 'Forbidden',
                message: `Access denied. Required roles: ${roles.join(', ')}`
            });
        }

        next();
    };
};

// Ensure user can only access their own shop's data
const ensureSameShop = (req, res, next) => {
    const shopId = req.params.shopId || req.body.shop_id || req.query.shop_id;

    if (!shopId) {
        return res.status(400).json({
            error: 'Bad Request',
            message: 'Shop ID is required'
        });
    }

    // Owners and admins can access any shop
    if (req.user.role === 'admin' || req.user.role === 'owner') {
        return next();
    }

    // Others can only access their own shop
    if (req.user.shop_id !== shopId) {
        return res.status(403).json({
            error: 'Forbidden',
            message: 'Access denied to this shop'
        });
    }

    next();
};

module.exports = {
    authenticate,
    authorize,
    ensureSameShop
};
