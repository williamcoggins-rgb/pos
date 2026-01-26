// API Configuration
// Change this to your deployed API URL in production
const API_URL = window.location.hostname === 'localhost'
    ? 'http://localhost:8000'
    : 'https://barberscore-pos-api.onrender.com'; // Change to your deployed API URL

// API Client
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

        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: 'Request failed' }));
            throw new Error(error.detail || error.error || 'Request failed');
        }

        return response.json();
    }

    // Auth
    async register(email, password, shopName) {
        const data = await this.request('/api/auth/register', {
            method: 'POST',
            body: JSON.stringify({ email, password, shop_name: shopName }),
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
        return !!this.token;
    }

    // POS
    async createSale() {
        return this.request('/api/pos/sales', {
            method: 'POST',
            body: JSON.stringify({
                barber_id: this.barberId,
                metadata: {},
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

    // Eligibility
    async getBarberScore() {
        return this.request(`/api/eligibility/score/${this.barberId}`);
    }

    async getEntitlements() {
        return this.request(`/api/eligibility/entitlements/${this.barberId}`);
    }

    async updateScore() {
        return this.request(`/api/eligibility/score/${this.barberId}/update`, {
            method: 'POST',
        });
    }
}

// Export for use in the app
window.APIClient = APIClient;
