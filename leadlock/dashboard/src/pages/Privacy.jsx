import { Link } from 'react-router-dom';
import { Zap, ArrowLeft } from 'lucide-react';

export default function Privacy() {
  const year = new Date().getFullYear();

  return (
    <div className="landing-dark min-h-screen">
      {/* Nav */}
      <nav className="border-b border-[#222230]">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <Link to="/" className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-orange-500 to-orange-600 flex items-center justify-center">
                <Zap className="w-4 h-4 text-white" strokeWidth={2.5} />
              </div>
              <span className="text-lg font-bold tracking-tight text-[#F8F8FC]">
                Lead<span className="text-orange-500">Lock</span>
              </span>
            </Link>
            <Link to="/" className="flex items-center gap-2 text-sm text-[#A1A1BC] hover:text-[#F8F8FC] transition-colors">
              <ArrowLeft className="w-4 h-4" /> Back
            </Link>
          </div>
        </div>
      </nav>

      {/* Content */}
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
        <h1 className="text-3xl font-black tracking-tight text-[#F8F8FC] mb-2" style={{ fontFamily: 'Inter, sans-serif' }}>
          Privacy Policy
        </h1>
        <p className="text-sm text-[#52526B] mb-12">Last updated: February {year}</p>

        <div className="space-y-10 text-sm leading-relaxed text-[#A1A1BC]">
          <section>
            <h2 className="text-lg font-bold text-[#F8F8FC] mb-3">1. Introduction</h2>
            <p>
              LeadLock ("we," "our," or "us") operates the LeadLock AI speed-to-lead platform
              (the "Service"). This Privacy Policy explains how we collect, use, disclose, and
              safeguard your information when you use our Service, including our website at
              leadlock.org and our dashboard application.
            </p>
          </section>

          <section>
            <h2 className="text-lg font-bold text-[#F8F8FC] mb-3">2. Information We Collect</h2>
            <h3 className="text-base font-semibold text-[#F8F8FC] mb-2">Account Information</h3>
            <p className="mb-3">
              When you create an account, we collect your business name, contact name, email
              address, phone number, trade type, and password (stored as a bcrypt hash).
            </p>

            <h3 className="text-base font-semibold text-[#F8F8FC] mb-2">Lead Data</h3>
            <p className="mb-3">
              When leads contact your business through our platform, we collect their name,
              phone number, email address (if provided), service request details, and
              conversation history. This data is processed on your behalf as a data processor.
            </p>

            <h3 className="text-base font-semibold text-[#F8F8FC] mb-2">Usage Data</h3>
            <p>
              We automatically collect information about how you interact with the Service,
              including login times, pages viewed, features used, and device information
              (browser type, IP address).
            </p>
          </section>

          <section>
            <h2 className="text-lg font-bold text-[#F8F8FC] mb-3">3. How We Use Your Information</h2>
            <ul className="list-disc list-inside space-y-2 ml-2">
              <li>To provide and maintain the Service, including AI-powered lead response and qualification</li>
              <li>To process and book appointments into your connected CRM</li>
              <li>To send transactional emails (lead notifications, booking confirmations, system alerts)</li>
              <li>To ensure TCPA, FTSA, and other regulatory compliance for SMS communications</li>
              <li>To maintain consent records as required by the FTC Telemarketing Sales Rule</li>
              <li>To improve and optimize our AI conversation models and response quality</li>
              <li>To provide customer support and respond to your inquiries</li>
              <li>To detect and prevent fraud, abuse, or security incidents</li>
            </ul>
          </section>

          <section>
            <h2 className="text-lg font-bold text-[#F8F8FC] mb-3">4. SMS & Communication Compliance</h2>
            <p className="mb-3">
              Our platform sends SMS messages on behalf of our clients to their leads. All SMS
              communications comply with:
            </p>
            <ul className="list-disc list-inside space-y-2 ml-2">
              <li><strong className="text-[#F8F8FC]">TCPA</strong> — Telephone Consumer Protection Act. Consent is tracked and recorded for every message.</li>
              <li><strong className="text-[#F8F8FC]">FTSA</strong> — Florida Telephone Solicitation Act. State-specific quiet hours and holiday restrictions enforced.</li>
              <li><strong className="text-[#F8F8FC]">Texas SB 140</strong> — Sunday texting restricted to noon-9 PM.</li>
              <li><strong className="text-[#F8F8FC]">California SB 1001</strong> — AI disclosure requirements met in all conversations.</li>
            </ul>
            <p className="mt-3">
              Every first message includes the business name and opt-out instructions ("Reply STOP to opt out").
              Consent records are retained for a minimum of 5 years per FTC TSR 2024 requirements.
            </p>
          </section>

          <section>
            <h2 className="text-lg font-bold text-[#F8F8FC] mb-3">5. Data Sharing & Disclosure</h2>
            <p className="mb-3">We do not sell your personal information. We may share data with:</p>
            <ul className="list-disc list-inside space-y-2 ml-2">
              <li><strong className="text-[#F8F8FC]">Service Providers</strong> — Twilio (SMS), Anthropic/OpenAI (AI processing), SendGrid (email), and your connected CRM provider</li>
              <li><strong className="text-[#F8F8FC]">CRM Integrations</strong> — Lead data is synced to your chosen CRM (ServiceTitan, Housecall Pro, Jobber, GoHighLevel) as configured by you</li>
              <li><strong className="text-[#F8F8FC]">Legal Requirements</strong> — When required by law, regulation, or legal process</li>
              <li><strong className="text-[#F8F8FC]">Business Transfers</strong> — In connection with a merger, acquisition, or sale of assets</li>
            </ul>
          </section>

          <section>
            <h2 className="text-lg font-bold text-[#F8F8FC] mb-3">6. Data Security</h2>
            <p>
              We implement industry-standard security measures to protect your data, including
              encryption of data in transit (TLS 1.2+) and at rest, bcrypt password hashing,
              PII masking in application logs (phone numbers show first 6 digits only), and
              role-based access controls. CRM API keys are stored encrypted. We conduct regular
              security reviews of our infrastructure.
            </p>
          </section>

          <section>
            <h2 className="text-lg font-bold text-[#F8F8FC] mb-3">7. Data Retention</h2>
            <ul className="list-disc list-inside space-y-2 ml-2">
              <li><strong className="text-[#F8F8FC]">Account data</strong> — Retained while your account is active and for 30 days after deletion</li>
              <li><strong className="text-[#F8F8FC]">Lead & conversation data</strong> — Retained for the duration of your subscription plus 90 days</li>
              <li><strong className="text-[#F8F8FC]">Consent records</strong> — Retained for 5 years per FTC TSR requirements, regardless of account status</li>
              <li><strong className="text-[#F8F8FC]">Usage logs</strong> — Retained for 12 months</li>
            </ul>
          </section>

          <section>
            <h2 className="text-lg font-bold text-[#F8F8FC] mb-3">8. Your Rights</h2>
            <p className="mb-3">Depending on your jurisdiction, you may have the right to:</p>
            <ul className="list-disc list-inside space-y-2 ml-2">
              <li>Access the personal data we hold about you</li>
              <li>Request correction of inaccurate data</li>
              <li>Request deletion of your data (subject to legal retention requirements)</li>
              <li>Export your data in a machine-readable format (CSV)</li>
              <li>Opt out of SMS communications by replying STOP to any message</li>
              <li>Withdraw consent for data processing</li>
            </ul>
            <p className="mt-3">
              To exercise these rights, contact us at privacy@leadlock.org.
            </p>
          </section>

          <section>
            <h2 className="text-lg font-bold text-[#F8F8FC] mb-3">9. Cookies & Tracking</h2>
            <p>
              Our dashboard application uses essential cookies for authentication (JWT session
              tokens stored in localStorage). We do not use third-party tracking cookies,
              advertising pixels, or analytics services that track individual users across
              websites.
            </p>
          </section>

          <section>
            <h2 className="text-lg font-bold text-[#F8F8FC] mb-3">10. AI Processing</h2>
            <p>
              Our Service uses artificial intelligence (Claude by Anthropic, with OpenAI as
              fallback) to generate SMS responses, qualify leads, and book appointments.
              AI-generated messages are reviewed for quality and compliance. Lead conversation
              data may be used to improve response quality but is never shared with third
              parties for their own purposes. Per California SB 1001, our AI-generated
              messages include appropriate disclosures.
            </p>
          </section>

          <section>
            <h2 className="text-lg font-bold text-[#F8F8FC] mb-3">11. Children's Privacy</h2>
            <p>
              Our Service is not directed to individuals under 18. We do not knowingly collect
              personal information from children. If you become aware that a child has provided
              us with personal data, please contact us at privacy@leadlock.org.
            </p>
          </section>

          <section>
            <h2 className="text-lg font-bold text-[#F8F8FC] mb-3">12. Changes to This Policy</h2>
            <p>
              We may update this Privacy Policy from time to time. We will notify you of any
              material changes by posting the updated policy on this page and updating the
              "Last updated" date. Your continued use of the Service after any changes
              constitutes acceptance of the updated policy.
            </p>
          </section>

          <section>
            <h2 className="text-lg font-bold text-[#F8F8FC] mb-3">13. Contact Us</h2>
            <p>
              If you have questions about this Privacy Policy or our data practices, contact us at:
            </p>
            <div className="mt-3 p-4 rounded-xl border border-[#222230] bg-[#111118]">
              <p className="text-[#F8F8FC] font-medium">LeadLock</p>
              <p className="mt-1">Email: privacy@leadlock.org</p>
              <p>Website: leadlock.org</p>
            </div>
          </section>
        </div>
      </div>

      {/* Footer */}
      <footer className="border-t border-[#222230] py-8">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <p className="text-xs text-[#52526B]">
            &copy; {year} LeadLock. All rights reserved.
          </p>
        </div>
      </footer>
    </div>
  );
}
