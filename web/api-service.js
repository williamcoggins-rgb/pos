// BarberScore POS API Service
// Handles all communication with backend API

const API_BASE_URL = 'https://pos-production-fd37.up.railway.app/api';

class APIService {
    constructor() {
        this.token = localStorage.getItem('auth_token');
    }

    // ============================================
    // UTILITY METHODS
    // ============================================

    setToken(token) {
        this.token = token;
        localStorage.setItem('auth_token', token);
    }

    clearToken() {
        this.token = null;
        localStorage.removeItem('auth_token');
    }

    getHeaders(includeAuth = true) {
        const headers = {
            'Content-Type': 'application/json'
        };

        if (includeAuth && this.token) {
            headers['Authorization'] = `Bearer ${this.token}`;
        }

        return headers;
    }

    async request(endpoint, options = {}) {
        const url = `${API_BASE_URL}${endpoint}`;
        const config = {
            ...options,
            headers: this.getHeaders(options.auth !== false)
        };

        try {
            const response = await fetch(url, config);

            // Handle 401 Unauthorized - token expired or invalid
            if (response.status === 401) {
                this.clearToken();
                throw new Error('Session expired. Please login again.');
            }

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.message || data.error || 'Request failed');
            }

            return data;
        } catch (error) {
            console.error('API Request Error:', error);
            throw error;
        }
    }

    // ============================================
    // AUTHENTICATION
    // ============================================

    async register(email, password, shopName, ownerName, phone) {
        const data = await this.request('/auth/register', {
            method: 'POST',
            auth: false,
            body: JSON.stringify({ email, password, shopName, ownerName, phone })
        });

        this.setToken(data.access_token);
        return data;
    }

    async login(email, password) {
        const data = await this.request('/auth/login', {
            method: 'POST',
            auth: false,
            body: JSON.stringify({ email, password })
        });

        this.setToken(data.access_token);
        return data;
    }

    async getCurrentUser() {
        return await this.request('/auth/me');
    }

    async changePassword(currentPassword, newPassword) {
        return await this.request('/auth/change-password', {
            method: 'POST',
            body: JSON.stringify({ currentPassword, newPassword })
        });
    }

    logout() {
        this.clearToken();
    }

    // ============================================
    // CUSTOMERS
    // ============================================

    async getCustomers(params = {}) {
        const query = new URLSearchParams(params).toString();
        return await this.request(`/customers?${query}`);
    }

    async getCustomer(id) {
        return await this.request(`/customers/${id}`);
    }

    async createCustomer(customerData) {
        return await this.request('/customers', {
            method: 'POST',
            body: JSON.stringify(customerData)
        });
    }

    async updateCustomer(id, updates) {
        return await this.request(`/customers/${id}`, {
            method: 'PATCH',
            body: JSON.stringify(updates)
        });
    }

    async deleteCustomer(id) {
        return await this.request(`/customers/${id}`, {
            method: 'DELETE'
        });
    }

    async getCustomerTransactions(id, limit = 20) {
        return await this.request(`/customers/${id}/transactions?limit=${limit}`);
    }

    // ============================================
    // TRANSACTIONS (SALES)
    // ============================================

    async getTransactions(params = {}) {
        const query = new URLSearchParams(params).toString();
        return await this.request(`/transactions?${query}`);
    }

    async getTransaction(id) {
        return await this.request(`/transactions/${id}`);
    }

    async createTransaction(transactionData) {
        return await this.request('/transactions', {
            method: 'POST',
            body: JSON.stringify(transactionData)
        });
    }

    async updateTransaction(id, updates) {
        return await this.request(`/transactions/${id}`, {
            method: 'PATCH',
            body: JSON.stringify(updates)
        });
    }

    async deleteTransaction(id) {
        return await this.request(`/transactions/${id}`, {
            method: 'DELETE'
        });
    }

    // ============================================
    // SERVICES
    // ============================================

    async getServices(params = {}) {
        const query = new URLSearchParams(params).toString();
        return await this.request(`/services?${query}`);
    }

    async getService(id) {
        return await this.request(`/services/${id}`);
    }

    async createService(serviceData) {
        return await this.request('/services', {
            method: 'POST',
            body: JSON.stringify(serviceData)
        });
    }

    async updateService(id, updates) {
        return await this.request(`/services/${id}`, {
            method: 'PATCH',
            body: JSON.stringify(updates)
        });
    }

    async deleteService(id) {
        return await this.request(`/services/${id}`, {
            method: 'DELETE'
        });
    }

    // ============================================
    // BARBERS (EMPLOYEES)
    // ============================================

    async getBarbers(params = {}) {
        const query = new URLSearchParams(params).toString();
        return await this.request(`/barbers?${query}`);
    }

    async getBarber(id) {
        return await this.request(`/barbers/${id}`);
    }

    async getBarberPerformance(id, startDate = null, endDate = null) {
        let query = '';
        if (startDate || endDate) {
            const params = new URLSearchParams();
            if (startDate) params.append('start_date', startDate);
            if (endDate) params.append('end_date', endDate);
            query = '?' + params.toString();
        }
        return await this.request(`/barbers/${id}/performance${query}`);
    }

    async createBarber(barberData) {
        return await this.request('/barbers', {
            method: 'POST',
            body: JSON.stringify(barberData)
        });
    }

    async updateBarber(id, updates) {
        return await this.request(`/barbers/${id}`, {
            method: 'PATCH',
            body: JSON.stringify(updates)
        });
    }

    async deleteBarber(id) {
        return await this.request(`/barbers/${id}`, {
            method: 'DELETE'
        });
    }

    // ============================================
    // APPOINTMENTS
    // ============================================

    async getAppointments(params = {}) {
        const query = new URLSearchParams(params).toString();
        return await this.request(`/appointments?${query}`);
    }

    async getAppointment(id) {
        return await this.request(`/appointments/${id}`);
    }

    async createAppointment(appointmentData) {
        return await this.request('/appointments', {
            method: 'POST',
            body: JSON.stringify(appointmentData)
        });
    }

    async updateAppointment(id, updates) {
        return await this.request(`/appointments/${id}`, {
            method: 'PATCH',
            body: JSON.stringify(updates)
        });
    }

    async deleteAppointment(id) {
        return await this.request(`/appointments/${id}`, {
            method: 'DELETE'
        });
    }

    // ============================================
    // PRODUCTS (INVENTORY)
    // ============================================

    async getProducts(params = {}) {
        const query = new URLSearchParams(params).toString();
        return await this.request(`/products?${query}`);
    }

    async getProduct(id) {
        return await this.request(`/products/${id}`);
    }

    async getProductHistory(id, limit = 50) {
        return await this.request(`/products/${id}/history?limit=${limit}`);
    }

    async createProduct(productData) {
        return await this.request('/products', {
            method: 'POST',
            body: JSON.stringify(productData)
        });
    }

    async updateProduct(id, updates) {
        return await this.request(`/products/${id}`, {
            method: 'PATCH',
            body: JSON.stringify(updates)
        });
    }

    async adjustInventory(id, quantityChange, transactionType, notes = '') {
        return await this.request(`/products/${id}/adjust`, {
            method: 'POST',
            body: JSON.stringify({ quantity_change: quantityChange, transaction_type: transactionType, notes })
        });
    }

    async deleteProduct(id) {
        return await this.request(`/products/${id}`, {
            method: 'DELETE'
        });
    }

    // ============================================
    // ANALYTICS
    // ============================================

    async getDashboardSummary(params = {}) {
        const query = new URLSearchParams(params).toString();
        return await this.request(`/analytics/dashboard?${query}`);
    }

    async getSalesByPeriod(period = 'day', params = {}) {
        const query = new URLSearchParams({ period, ...params }).toString();
        return await this.request(`/analytics/sales-by-period?${query}`);
    }

    async getTopServices(params = {}) {
        const query = new URLSearchParams(params).toString();
        return await this.request(`/analytics/top-services?${query}`);
    }

    async getTopCustomers(limit = 10) {
        return await this.request(`/analytics/top-customers?limit=${limit}`);
    }

    async getBarberLeaderboard(params = {}) {
        const query = new URLSearchParams(params).toString();
        return await this.request(`/analytics/barber-leaderboard?${query}`);
    }

    async getPaymentMethods(params = {}) {
        const query = new URLSearchParams(params).toString();
        return await this.request(`/analytics/payment-methods?${query}`);
    }

    async calculateBarberScore(barberId = null) {
        const query = barberId ? `?barber_id=${barberId}` : '';
        return await this.request(`/analytics/barberscore${query}`);
    }

    // ============================================
    // SHOPS
    // ============================================

    async getShop(id) {
        return await this.request(`/shops/${id}`);
    }

    async updateShop(id, updates) {
        return await this.request(`/shops/${id}`, {
            method: 'PATCH',
            body: JSON.stringify(updates)
        });
    }
}

// Export singleton instance
const api = new APIService();
