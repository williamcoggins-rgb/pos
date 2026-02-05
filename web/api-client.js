// API Configuration
// Auto-detects local dev vs production deployment
const API_URL = window.location.hostname === 'localhost'
    ? 'http://localhost:8000'
    : 'https://barberscore-pos-api.onrender.com';

// API Client - communicates with the event-sourced FastAPI backend
class APIClient {
    constructor() {
        this.token = localStorage.getItem('auth_token');
        this.barberId = localStorage.getItem('barber_id');
        this.shopName = localStorage.getItem('shop_name');
    }

    async request(endpoint, options = {}) {
        const headers = {
            'Content-Type': 'application/json',
            ...options.headers,
        };

        if (this.token) {
            headers['Authorization'] = `Bearer ${this.token}`;
        }

        const response = await fetch(`${API_URL}${endpoint}`, {
            ...options,
            headers,
        });

        if (response.status === 401) {
            // Token expired or invalid
            this.logout();
            throw new Error('Session expired. Please login again.');
        }

        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: 'Request failed' }));
            throw new Error(error.detail || error.error || 'Request failed');
        }

        return response.json();
    }

    // ============================================
    // AUTH
    // ============================================

    async register(email, password, shopName, ownerName, phone) {
        const data = await this.request('/api/auth/register', {
            method: 'POST',
            body: JSON.stringify({
                email,
                password,
                shopName,
                ownerName,
                phone,
            }),
        });

        this.setAuth(data);
        return data;
    }

    async login(email, password) {
        const data = await this.request('/api/auth/login', {
            method: 'POST',
            body: JSON.stringify({ email, password }),
        });

        this.setAuth(data);
        return data;
    }

    async loginWithPin(email, pin) {
        const data = await this.request('/api/auth/login-pin', {
            method: 'POST',
            body: JSON.stringify({ email, pin }),
        });

        this.setAuth(data);
        return data;
    }

    async setPin(pin) {
        return this.request('/api/auth/set-pin', {
            method: 'POST',
            body: JSON.stringify({ pin }),
        });
    }

    async getProfile() {
        return this.request('/api/auth/profile');
    }

    setAuth(data) {
        this.token = data.access_token;
        this.barberId = data.barber_id;
        this.shopName = data.shop_name;

        localStorage.setItem('auth_token', data.access_token);
        localStorage.setItem('barber_id', data.barber_id);
        localStorage.setItem('shop_name', data.shop_name);
    }

    logout() {
        this.token = null;
        this.barberId = null;
        this.shopName = null;

        localStorage.removeItem('auth_token');
        localStorage.removeItem('barber_id');
        localStorage.removeItem('shop_name');
    }

    isAuthenticated() {
        return !!this.token && !!this.barberId;
    }

    // ============================================
    // POS - Sales
    // ============================================

    async createSale(metadata = {}) {
        return this.request('/api/pos/sales', {
            method: 'POST',
            body: JSON.stringify({
                barber_id: this.barberId,
                metadata,
            }),
        });
    }

    async addLineItem(saleId, name, quantity, unitPriceCents) {
        return this.request(`/api/pos/sales/${saleId}/items`, {
            method: 'POST',
            body: JSON.stringify({
                name,
                quantity,
                unit_price_cents: unitPriceCents,
            }),
        });
    }

    async applyDiscount(saleId, amountCents, reason = '') {
        return this.request(`/api/pos/sales/${saleId}/discount`, {
            method: 'POST',
            body: JSON.stringify({
                amount_cents: amountCents,
                reason,
            }),
        });
    }

    async calculateTax(saleId, taxRate = 0.08) {
        return this.request(`/api/pos/sales/${saleId}/tax`, {
            method: 'POST',
            body: JSON.stringify({ tax_rate: taxRate }),
        });
    }

    async processPayment(saleId, paymentMethod = 'CASH', readerId = null) {
        return this.request(`/api/pos/sales/${saleId}/payment`, {
            method: 'POST',
            body: JSON.stringify({
                payment_method: paymentMethod,
                reader_id: readerId,
            }),
        });
    }

    async getSale(saleId) {
        return this.request(`/api/pos/sales/${saleId}`);
    }

    async listSales(since = null, limit = 50) {
        let url = `/api/pos/sales?limit=${limit}`;
        if (since) url += `&since=${encodeURIComponent(since)}`;
        return this.request(url);
    }

    async getAnalytics(since = null) {
        let url = '/api/pos/analytics';
        if (since) url += `?since=${encodeURIComponent(since)}`;
        return this.request(url);
    }

    // Refund & Void
    async createRefund(saleId, amountCents, reason = '', paymentIntentId = null) {
        return this.request(`/api/pos/sales/${saleId}/refund`, {
            method: 'POST',
            body: JSON.stringify({
                amount_cents: amountCents,
                reason,
                payment_intent_id: paymentIntentId,
            }),
        });
    }

    async voidSale(saleId, reason = '') {
        return this.request(`/api/pos/sales/${saleId}/void`, {
            method: 'POST',
            body: JSON.stringify({ reason }),
        });
    }

    // ============================================
    // ELIGIBILITY - BarberScore & Entitlements
    // ============================================

    async getBarberScore() {
        return this.request(`/api/eligibility/score/${this.barberId}`);
    }

    async updateScore() {
        return this.request(`/api/eligibility/score/${this.barberId}/update`, {
            method: 'POST',
        });
    }

    async getEntitlements() {
        return this.request(`/api/eligibility/entitlements/${this.barberId}`);
    }

    async getUnlockRequirements(tier) {
        return this.request(`/api/eligibility/unlock-requirements/${this.barberId}/${tier}`);
    }

    // ============================================
    // PROCUREMENT (Signal-Based)
    // ============================================

    async getProcurementStatus() {
        return this.request('/api/procurement/status');
    }

    async signalReadiness(contactPreference = 'email', message = '') {
        return this.request('/api/procurement/signal', {
            method: 'POST',
            body: JSON.stringify({
                contact_preference: contactPreference,
                message,
            }),
        });
    }

    async listSignals() {
        return this.request('/api/procurement/signals');
    }

    async getSignal(signalId) {
        return this.request(`/api/procurement/signals/${signalId}`);
    }

    // ============================================
    // STRIPE CONNECT
    // ============================================

    async getStripeAccountStatus() {
        return this.request('/api/stripe/account-status');
    }

    async createStripeAccountLink() {
        return this.request('/api/stripe/create-account-link', {
            method: 'POST',
        });
    }
}

// Export for use in the app
window.APIClient = APIClient;
