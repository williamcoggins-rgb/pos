const nodemailer = require('nodemailer');

// Create email transporter
let transporter;

if (process.env.EMAIL_HOST && process.env.EMAIL_USER && process.env.EMAIL_PASSWORD) {
    transporter = nodemailer.createTransport({
        host: process.env.EMAIL_HOST,
        port: parseInt(process.env.EMAIL_PORT) || 587,
        secure: process.env.EMAIL_SECURE === 'true',
        auth: {
            user: process.env.EMAIL_USER,
            pass: process.env.EMAIL_PASSWORD
        }
    });
} else if (process.env.NODE_ENV === 'development') {
    // Use ethereal email for testing
    console.log('Email not configured, will use console logging instead');
}

async function sendEmail({ to, subject, html, text }) {
    if (!transporter) {
        // In development or if email not configured, just log
        console.log('\n=== EMAIL WOULD BE SENT ===');
        console.log('To:', to);
        console.log('Subject:', subject);
        console.log('Body:', text || html);
        console.log('===========================\n');
        return { messageId: 'dev-mode-no-email' };
    }

    try {
        const info = await transporter.sendMail({
            from: process.env.EMAIL_FROM || '"BarberScore POS" <noreply@barberscore.com>',
            to,
            subject,
            text,
            html
        });

        console.log('Email sent:', info.messageId);
        return info;
    } catch (error) {
        console.error('Email send error:', error);
        throw error;
    }
}

async function sendStripeOnboardingEmail(email, onboardingUrl, userName) {
    const subject = 'Complete Your Payment Setup - BarberScore POS';

    const html = `
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                }
                .header {
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 30px;
                    border-radius: 10px 10px 0 0;
                    text-align: center;
                }
                .content {
                    background: #f9f9f9;
                    padding: 30px;
                    border-radius: 0 0 10px 10px;
                }
                .button {
                    display: inline-block;
                    background: #667eea;
                    color: white;
                    padding: 15px 30px;
                    text-decoration: none;
                    border-radius: 8px;
                    margin: 20px 0;
                    font-weight: bold;
                }
                .footer {
                    margin-top: 30px;
                    padding-top: 20px;
                    border-top: 1px solid #ddd;
                    font-size: 12px;
                    color: #666;
                }
            </style>
        </head>
        <body>
            <div class="header">
                <h1>💳 Payment Setup Required</h1>
            </div>
            <div class="content">
                <p>Hi ${userName},</p>

                <p>Welcome to BarberScore POS! To start accepting payments from your clients, you need to complete a quick setup with our payment processor, Stripe.</p>

                <p><strong>What you need to set up:</strong></p>
                <ul>
                    <li>Bank account details (where you'll receive payments)</li>
                    <li>Tax ID or SSN (required by law)</li>
                    <li>Business information</li>
                </ul>

                <p><strong>This takes about 2-3 minutes.</strong></p>

                <p style="text-align: center;">
                    <a href="${onboardingUrl}" class="button">Complete Payment Setup</a>
                </p>

                <p><strong>Why Stripe?</strong></p>
                <ul>
                    <li>✅ Industry standard (trusted by millions)</li>
                    <li>✅ Secure & PCI compliant</li>
                    <li>✅ Money deposited to your bank in 2 days</li>
                    <li>✅ Accept all major cards, Apple Pay, Google Pay</li>
                </ul>

                <p>If you have any questions, just reply to this email!</p>

                <p>Thanks,<br>The BarberScore Team</p>
            </div>
            <div class="footer">
                <p>This link will expire in 7 days. If you need a new link, contact support.</p>
            </div>
        </body>
        </html>
    `;

    const text = `
Hi ${userName},

Welcome to BarberScore POS! To start accepting payments, please complete your payment setup with Stripe:

${onboardingUrl}

What you need:
- Bank account details
- Tax ID or SSN
- Business information

This takes about 2-3 minutes.

Thanks,
The BarberScore Team
    `;

    return await sendEmail({ to: email, subject, html, text });
}

async function sendWelcomeEmail(email, userName) {
    const subject = 'Welcome to BarberScore POS!';

    const html = `
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                }
                .header {
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 30px;
                    border-radius: 10px 10px 0 0;
                    text-align: center;
                }
                .content {
                    background: #f9f9f9;
                    padding: 30px;
                    border-radius: 0 0 10px 10px;
                }
            </style>
        </head>
        <body>
            <div class="header">
                <h1>🎉 Welcome to BarberScore!</h1>
            </div>
            <div class="content">
                <p>Hi ${userName},</p>

                <p>Your BarberScore POS account has been created successfully!</p>

                <p><strong>Next steps:</strong></p>
                <ol>
                    <li>Check your email for payment setup instructions</li>
                    <li>Complete your Stripe payment setup (2-3 minutes)</li>
                    <li>Start accepting payments from clients!</li>
                </ol>

                <p>If you have any questions, just reply to this email.</p>

                <p>Cheers,<br>The BarberScore Team</p>
            </div>
        </body>
        </html>
    `;

    const text = `
Hi ${userName},

Welcome to BarberScore POS! Your account has been created successfully.

Next steps:
1. Check your email for payment setup instructions
2. Complete your Stripe payment setup
3. Start accepting payments!

Thanks,
The BarberScore Team
    `;

    return await sendEmail({ to: email, subject, html, text });
}

module.exports = {
    sendEmail,
    sendStripeOnboardingEmail,
    sendWelcomeEmail
};
