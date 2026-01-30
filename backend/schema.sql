-- BarberScore POS Database Schema
-- PostgreSQL 14+

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================
-- USERS & AUTHENTICATION
-- ============================================

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL CHECK (role IN ('owner', 'manager', 'barber', 'admin')),
    shop_id UUID, -- Will be foreign key to shops table
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    last_login TIMESTAMP,
    is_active BOOLEAN DEFAULT true
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_shop_id ON users(shop_id);

-- ============================================
-- SHOPS/LOCATIONS
-- ============================================

CREATE TABLE shops (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    owner_id UUID REFERENCES users(id),
    address TEXT,
    phone VARCHAR(50),
    email VARCHAR(255),
    timezone VARCHAR(50) DEFAULT 'America/New_York',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    is_active BOOLEAN DEFAULT true
);

-- Add foreign key to users table
ALTER TABLE users ADD CONSTRAINT fk_users_shop
    FOREIGN KEY (shop_id) REFERENCES shops(id) ON DELETE SET NULL;

CREATE INDEX idx_shops_owner ON shops(owner_id);

-- ============================================
-- CUSTOMERS
-- ============================================

CREATE TABLE customers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    shop_id UUID REFERENCES shops(id) ON DELETE CASCADE,
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    email VARCHAR(255),
    phone VARCHAR(50),
    notes TEXT,
    preferences JSONB, -- Hair preferences, product allergies, etc.
    lifetime_value DECIMAL(10,2) DEFAULT 0.00,
    visit_count INTEGER DEFAULT 0,
    first_visit_date TIMESTAMP,
    last_visit_date TIMESTAMP,
    preferred_barber_id UUID, -- Will be foreign key to barbers table
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    is_active BOOLEAN DEFAULT true
);

CREATE INDEX idx_customers_shop ON customers(shop_id);
CREATE INDEX idx_customers_email ON customers(email);
CREATE INDEX idx_customers_phone ON customers(phone);
CREATE INDEX idx_customers_name ON customers(first_name, last_name);

-- ============================================
-- BARBERS (Employees)
-- ============================================

CREATE TABLE barbers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    shop_id UUID REFERENCES shops(id) ON DELETE CASCADE,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    email VARCHAR(255),
    phone VARCHAR(50),
    commission_rate DECIMAL(5,2) DEFAULT 0.00, -- Percentage (e.g., 50.00 = 50%)
    hourly_rate DECIMAL(10,2),
    hire_date DATE,
    bio TEXT,
    specialties TEXT[],
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Add foreign key to customers table
ALTER TABLE customers ADD CONSTRAINT fk_customers_preferred_barber
    FOREIGN KEY (preferred_barber_id) REFERENCES barbers(id) ON DELETE SET NULL;

CREATE INDEX idx_barbers_shop ON barbers(shop_id);
CREATE INDEX idx_barbers_user ON barbers(user_id);

-- ============================================
-- SERVICES
-- ============================================

CREATE TABLE services (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    shop_id UUID REFERENCES shops(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    price DECIMAL(10,2) NOT NULL,
    duration_minutes INTEGER DEFAULT 30,
    category VARCHAR(100), -- 'haircut', 'beard', 'color', 'addon', etc.
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_services_shop ON services(shop_id);
CREATE INDEX idx_services_category ON services(category);

-- ============================================
-- APPOINTMENTS
-- ============================================

CREATE TABLE appointments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    shop_id UUID REFERENCES shops(id) ON DELETE CASCADE,
    customer_id UUID REFERENCES customers(id) ON DELETE SET NULL,
    barber_id UUID REFERENCES barbers(id) ON DELETE SET NULL,
    scheduled_start TIMESTAMP NOT NULL,
    scheduled_end TIMESTAMP NOT NULL,
    status VARCHAR(50) DEFAULT 'scheduled' CHECK (status IN ('scheduled', 'confirmed', 'in_progress', 'completed', 'no_show', 'cancelled')),
    notes TEXT,
    reminder_sent BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_appointments_shop ON appointments(shop_id);
CREATE INDEX idx_appointments_customer ON appointments(customer_id);
CREATE INDEX idx_appointments_barber ON appointments(barber_id);
CREATE INDEX idx_appointments_start ON appointments(scheduled_start);
CREATE INDEX idx_appointments_status ON appointments(status);

-- ============================================
-- APPOINTMENT SERVICES (Many-to-Many)
-- ============================================

CREATE TABLE appointment_services (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    appointment_id UUID REFERENCES appointments(id) ON DELETE CASCADE,
    service_id UUID REFERENCES services(id) ON DELETE CASCADE,
    price DECIMAL(10,2) NOT NULL, -- Price at time of booking
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_appt_services_appointment ON appointment_services(appointment_id);
CREATE INDEX idx_appt_services_service ON appointment_services(service_id);

-- ============================================
-- TRANSACTIONS (Sales)
-- ============================================

CREATE TABLE transactions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    shop_id UUID REFERENCES shops(id) ON DELETE CASCADE,
    customer_id UUID REFERENCES customers(id) ON DELETE SET NULL,
    barber_id UUID REFERENCES barbers(id) ON DELETE SET NULL,
    appointment_id UUID REFERENCES appointments(id) ON DELETE SET NULL,
    transaction_date TIMESTAMP DEFAULT NOW(),
    subtotal DECIMAL(10,2) NOT NULL,
    tax DECIMAL(10,2) DEFAULT 0.00,
    tip DECIMAL(10,2) DEFAULT 0.00,
    discount DECIMAL(10,2) DEFAULT 0.00,
    total DECIMAL(10,2) NOT NULL,
    payment_method VARCHAR(50), -- 'tap_to_pay', 'apple_pay', 'cash_app', 'invoice', 'cash', 'card'
    payment_status VARCHAR(50) DEFAULT 'completed' CHECK (payment_status IN ('pending', 'completed', 'refunded', 'failed')),
    notes TEXT,
    -- BarberScore tracking
    client_rebooked BOOLEAN DEFAULT false,
    had_retail BOOLEAN DEFAULT false,
    had_addons BOOLEAN DEFAULT false,
    is_no_show BOOLEAN DEFAULT false,
    is_cancelled BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_transactions_shop ON transactions(shop_id);
CREATE INDEX idx_transactions_customer ON transactions(customer_id);
CREATE INDEX idx_transactions_barber ON transactions(barber_id);
CREATE INDEX idx_transactions_date ON transactions(transaction_date);
CREATE INDEX idx_transactions_payment_method ON transactions(payment_method);

-- ============================================
-- TRANSACTION ITEMS
-- ============================================

CREATE TABLE transaction_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    transaction_id UUID REFERENCES transactions(id) ON DELETE CASCADE,
    service_id UUID REFERENCES services(id) ON DELETE SET NULL,
    product_id UUID, -- Will be foreign key to products table
    item_type VARCHAR(50) NOT NULL CHECK (item_type IN ('service', 'product')),
    name VARCHAR(255) NOT NULL, -- Store name at time of sale
    quantity INTEGER DEFAULT 1,
    unit_price DECIMAL(10,2) NOT NULL,
    total_price DECIMAL(10,2) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_transaction_items_transaction ON transaction_items(transaction_id);
CREATE INDEX idx_transaction_items_service ON transaction_items(service_id);

-- ============================================
-- PRODUCTS (Inventory)
-- ============================================

CREATE TABLE products (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    shop_id UUID REFERENCES shops(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    sku VARCHAR(100),
    category VARCHAR(100), -- 'shampoo', 'conditioner', 'pomade', 'tools', etc.
    cost_price DECIMAL(10,2),
    retail_price DECIMAL(10,2) NOT NULL,
    quantity_in_stock INTEGER DEFAULT 0,
    reorder_level INTEGER DEFAULT 5,
    reorder_quantity INTEGER DEFAULT 10,
    supplier VARCHAR(255),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Add foreign key to transaction_items table
ALTER TABLE transaction_items ADD CONSTRAINT fk_transaction_items_product
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE SET NULL;

CREATE INDEX idx_products_shop ON products(shop_id);
CREATE INDEX idx_products_sku ON products(sku);
CREATE INDEX idx_products_category ON products(category);

-- ============================================
-- INVENTORY TRANSACTIONS
-- ============================================

CREATE TABLE inventory_transactions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_id UUID REFERENCES products(id) ON DELETE CASCADE,
    shop_id UUID REFERENCES shops(id) ON DELETE CASCADE,
    transaction_type VARCHAR(50) NOT NULL CHECK (transaction_type IN ('purchase', 'sale', 'adjustment', 'return', 'waste')),
    quantity_change INTEGER NOT NULL, -- Positive for additions, negative for reductions
    unit_cost DECIMAL(10,2),
    notes TEXT,
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_inventory_transactions_product ON inventory_transactions(product_id);
CREATE INDEX idx_inventory_transactions_shop ON inventory_transactions(shop_id);
CREATE INDEX idx_inventory_transactions_date ON inventory_transactions(created_at);

-- ============================================
-- BARBERSCORE METRICS (Tracking)
-- ============================================

CREATE TABLE barberscore_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    shop_id UUID REFERENCES shops(id) ON DELETE CASCADE,
    barber_id UUID REFERENCES barbers(id) ON DELETE SET NULL,
    calculation_date DATE NOT NULL,
    score INTEGER NOT NULL,
    tier INTEGER NOT NULL,
    tier_name VARCHAR(100),
    -- Score breakdown
    rebook_rate DECIMAL(5,2),
    retail_rate DECIMAL(5,2),
    addon_rate DECIMAL(5,2),
    completion_rate DECIMAL(5,2),
    avg_transaction_value DECIMAL(10,2),
    days_active INTEGER,
    unique_days_worked INTEGER,
    total_transactions INTEGER,
    total_revenue DECIMAL(10,2),
    metadata JSONB, -- Store full calculation details
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_barberscore_shop ON barberscore_metrics(shop_id);
CREATE INDEX idx_barberscore_barber ON barberscore_metrics(barber_id);
CREATE INDEX idx_barberscore_date ON barberscore_metrics(calculation_date);

-- ============================================
-- AUDIT LOGS
-- ============================================

CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    shop_id UUID REFERENCES shops(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    action VARCHAR(100) NOT NULL, -- 'create', 'update', 'delete', 'login', etc.
    entity_type VARCHAR(100), -- 'transaction', 'customer', 'appointment', etc.
    entity_id UUID,
    changes JSONB, -- Store before/after values
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_audit_logs_shop ON audit_logs(shop_id);
CREATE INDEX idx_audit_logs_user ON audit_logs(user_id);
CREATE INDEX idx_audit_logs_date ON audit_logs(created_at);
CREATE INDEX idx_audit_logs_entity ON audit_logs(entity_type, entity_id);

-- ============================================
-- FUNCTIONS & TRIGGERS
-- ============================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Add triggers to all tables with updated_at
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_shops_updated_at BEFORE UPDATE ON shops FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_customers_updated_at BEFORE UPDATE ON customers FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_barbers_updated_at BEFORE UPDATE ON barbers FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_services_updated_at BEFORE UPDATE ON services FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_appointments_updated_at BEFORE UPDATE ON appointments FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_transactions_updated_at BEFORE UPDATE ON transactions FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_products_updated_at BEFORE UPDATE ON products FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================
-- VIEWS FOR COMMON QUERIES
-- ============================================

-- Customer lifetime value view
CREATE VIEW customer_stats AS
SELECT
    c.id,
    c.shop_id,
    c.first_name,
    c.last_name,
    c.email,
    c.phone,
    COUNT(DISTINCT t.id) as total_visits,
    COALESCE(SUM(t.total), 0) as lifetime_value,
    COALESCE(AVG(t.total), 0) as avg_transaction_value,
    MAX(t.transaction_date) as last_visit_date,
    MIN(t.transaction_date) as first_visit_date,
    COUNT(DISTINCT CASE WHEN t.client_rebooked THEN t.id END) as rebook_count
FROM customers c
LEFT JOIN transactions t ON c.id = t.customer_id AND t.payment_status = 'completed'
GROUP BY c.id;

-- Barber performance view
CREATE VIEW barber_performance AS
SELECT
    b.id,
    b.shop_id,
    b.first_name,
    b.last_name,
    COUNT(DISTINCT t.id) as total_transactions,
    COALESCE(SUM(t.total), 0) as total_revenue,
    COALESCE(AVG(t.total), 0) as avg_transaction_value,
    COUNT(DISTINCT t.customer_id) as unique_customers,
    COUNT(DISTINCT CASE WHEN t.client_rebooked THEN t.id END) as rebook_count,
    COALESCE(COUNT(DISTINCT CASE WHEN t.client_rebooked THEN t.id END)::DECIMAL / NULLIF(COUNT(DISTINCT t.id), 0) * 100, 0) as rebook_rate
FROM barbers b
LEFT JOIN transactions t ON b.id = t.barber_id AND t.payment_status = 'completed'
GROUP BY b.id;

-- Daily sales summary view
CREATE VIEW daily_sales_summary AS
SELECT
    shop_id,
    DATE(transaction_date) as sale_date,
    COUNT(DISTINCT id) as transaction_count,
    COUNT(DISTINCT customer_id) as unique_customers,
    COALESCE(SUM(total), 0) as total_revenue,
    COALESCE(SUM(tax), 0) as total_tax,
    COALESCE(SUM(tip), 0) as total_tips,
    COALESCE(AVG(total), 0) as avg_transaction_value
FROM transactions
WHERE payment_status = 'completed'
GROUP BY shop_id, DATE(transaction_date);
