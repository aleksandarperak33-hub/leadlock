import { Link } from 'react-router-dom';
import { Zap, ArrowLeft } from 'lucide-react';
import SEO from '../components/SEO';

export default function Terms() {
  return (
    <div className="landing-dark min-h-screen">
      <SEO
        title="Terms of Service"
        description="Terms governing use of the LeadLock AI speed-to-lead platform. Billing, SMS compliance, AI disclosure, and service agreements."
        path="/terms"
      />

      <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        {/* Header */}
        <div className="flex items-center gap-3 mb-8">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-orange-500 to-orange-600 flex items-center justify-center">
            <Zap className="w-4 h-4 text-white" strokeWidth={2.5} />
          </div>
          <span className="text-lg font-bold text-[#F8F8FC]">
            Lead<span className="text-orange-500">Lock</span>
          </span>
        </div>

        <Link to="/" className="inline-flex items-center gap-1.5 text-sm text-[#A1A1BC] hover:text-[#F8F8FC] mb-8 transition-colors">
          <ArrowLeft className="w-4 h-4" /> Back to home
        </Link>

        <h1 className="text-3xl font-bold text-[#F8F8FC] mb-8">Terms of Service</h1>

        <div className="prose prose-invert prose-sm max-w-none space-y-6 text-[#A1A1BC] leading-relaxed">
          <p><strong className="text-[#F8F8FC]">Last updated:</strong> February 23, 2026</p>

          <h2 className="text-lg font-semibold text-[#F8F8FC]">1. Acceptance of Terms</h2>
          <p>By creating an account or using LeadLock ("Service"), you agree to be bound by these Terms of Service. If you do not agree, do not use the Service.</p>

          <h2 className="text-lg font-semibold text-[#F8F8FC]">2. Description of Service</h2>
          <p>LeadLock provides AI-powered lead response, qualification, and appointment booking services for home services businesses via SMS and integrated CRM systems.</p>

          <h2 className="text-lg font-semibold text-[#F8F8FC]">3. Account Responsibilities</h2>
          <p>You are responsible for maintaining the security of your account credentials. You agree to provide accurate business information for SMS compliance (TCPA, 10DLC). You must not use the Service for any unlawful purpose.</p>

          <h2 className="text-lg font-semibold text-[#F8F8FC]">4. Billing and Payments</h2>
          <p>Subscription fees are billed monthly. Failure to pay may result in service suspension. You may cancel at any time; cancellation takes effect at the end of the current billing period. No refunds for partial months.</p>

          <h2 className="text-lg font-semibold text-[#F8F8FC]">5. SMS Compliance & Consent</h2>
          <p>You agree to comply with all applicable SMS regulations including TCPA, FTSA, and state-specific laws. LeadLock provides compliance tools, but you are ultimately responsible for the content and recipients of messages sent on your behalf.</p>

          <h3 className="text-base font-medium text-[#F8F8FC] mt-4">SMS Consent</h3>
          <p>By submitting your phone number through a web form, you consent to receive SMS messages related to your service inquiry. Promotional or marketing messages will only be sent with your separate express written consent. SMS consent is voluntary and is not a condition of purchasing any goods or services.</p>

          <h3 className="text-base font-medium text-[#F8F8FC] mt-4">Message Details</h3>
          <ul className="list-disc list-inside space-y-1 ml-2">
            <li>Message frequency varies based on your service inquiry and appointment status.</li>
            <li>Message and data rates may apply.</li>
            <li>Reply STOP to cancel SMS messages at any time.</li>
            <li>Reply HELP for assistance.</li>
            <li>Carriers are not liable for delayed or undelivered messages.</li>
          </ul>

          <h3 className="text-base font-medium text-[#F8F8FC] mt-4">Data Protection</h3>
          <p>LeadLock does not sell, rent, or share your phone number with third parties for their marketing purposes. Your phone number is used solely to provide the services you requested and to communicate about your service inquiry.</p>

          <h2 className="text-lg font-semibold text-[#F8F8FC]">6. AI Disclosure</h2>
          <p>Messages sent by LeadLock on your behalf may include AI-generated content. Per California SB 1001 and similar regulations, we disclose AI involvement when required.</p>

          <h2 className="text-lg font-semibold text-[#F8F8FC]">7. Limitation of Liability</h2>
          <p>LeadLock shall not be liable for indirect, incidental, special, or consequential damages. Our total liability shall not exceed the fees paid by you in the 12 months preceding the claim.</p>

          <h2 className="text-lg font-semibold text-[#F8F8FC]">8. Termination</h2>
          <p>Either party may terminate this agreement at any time. Upon termination, your access to the Service will cease. We retain compliance records (consent, opt-outs) for the legally required period (5 years).</p>

          <h2 className="text-lg font-semibold text-[#F8F8FC]">9. Changes to Terms</h2>
          <p>We may update these Terms from time to time. Continued use after changes constitutes acceptance. Material changes will be communicated via email.</p>

          <h2 className="text-lg font-semibold text-[#F8F8FC]">10. Contact</h2>
          <p>Questions about these Terms? Contact us at <a href="mailto:legal@leadlock.org" className="text-orange-400 hover:text-orange-300">legal@leadlock.org</a>.</p>
        </div>
      </div>
    </div>
  );
}
