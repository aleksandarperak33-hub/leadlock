import { Link } from 'react-router-dom';
import { Zap, ArrowLeft, MessageSquare, Bot, Calendar, TrendingUp, Mail, MapPin, ExternalLink } from 'lucide-react';
import SEO from '../components/SEO';

const STEPS = [
  {
    icon: MessageSquare,
    title: 'Instant Response',
    desc: 'A lead comes in via web form, phone call, or text message. Our AI responds in under 10 seconds with a personalized message.',
  },
  {
    icon: Bot,
    title: 'AI Qualification',
    desc: 'Conversational AI identifies the service type, urgency, and timeline in 4 messages or fewer.',
  },
  {
    icon: Calendar,
    title: 'Auto-Booking',
    desc: 'The system checks real-time availability and books an appointment directly into your CRM.',
  },
  {
    icon: TrendingUp,
    title: 'Smart Follow-Up',
    desc: 'Cold leads receive automated nurture sequences. Warm leads get priority routing to your team.',
  },
];

export default function About() {
  const year = new Date().getFullYear();

  return (
    <div className="landing-dark min-h-screen">
      <SEO
        title="About LeadLock"
        description="AI-powered speed-to-lead platform built for home services contractors. Respond to every lead in under 60 seconds, qualify with AI, and book appointments automatically."
        path="/about"
      />

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
          About LeadLock
        </h1>
        <p className="text-sm text-[#52526B] mb-12">AI-powered speed-to-lead for home services</p>

        <div className="space-y-12 text-sm leading-relaxed text-[#A1A1BC]">
          {/* Who We Are */}
          <section>
            <h2 className="text-lg font-bold text-[#F8F8FC] mb-3">Who We Are</h2>
            <p>
              LeadLock is an AI-powered speed-to-lead platform built for home services contractors.
              Founded in 2024, we help HVAC, plumbing, roofing, electrical, and solar businesses
              respond to every inbound lead in under 60 seconds. Our platform qualifies leads through
              natural AI conversation, books appointments directly into your CRM, and runs automated
              follow-up sequences so no lead ever falls through the cracks.
            </p>
          </section>

          {/* Our Mission */}
          <section>
            <h2 className="text-lg font-bold text-[#F8F8FC] mb-3">Our Mission</h2>
            <p>
              Every missed lead is lost revenue. Research shows that responding within 60 seconds
              makes you 21x more likely to book the job, yet the average contractor takes over 4
              hours to follow up. We built LeadLock so contractors never lose a customer to a slow
              response again.
            </p>
          </section>

          {/* How It Works */}
          <section>
            <h2 className="text-lg font-bold text-[#F8F8FC] mb-4">How It Works</h2>
            <div className="grid sm:grid-cols-2 gap-4">
              {STEPS.map((step, i) => (
                <div key={i} className="flex gap-4 p-4 rounded-xl border border-[#222230] bg-[#111118]">
                  <div className="w-10 h-10 rounded-xl bg-orange-500/10 flex items-center justify-center flex-shrink-0">
                    <step.icon className="w-5 h-5 text-orange-400" />
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold text-[#F8F8FC] mb-1">
                      {i + 1}. {step.title}
                    </h3>
                    <p className="text-xs text-[#A1A1BC] leading-relaxed">{step.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* Compliance */}
          <section>
            <h2 className="text-lg font-bold text-[#F8F8FC] mb-3">Built on Compliance</h2>
            <p>
              TCPA violations carry penalties of $500 to $1,500 per message with no cap. Compliance
              is not optional in this industry. Every message LeadLock sends is checked against
              federal and state regulations before delivery. We enforce consent tracking, opt-out
              processing, quiet hours, AI disclosure (California SB 1001), and maintain consent
              records for 5 years per FTC requirements.
            </p>
          </section>

          {/* Contact Us */}
          <section>
            <h2 className="text-lg font-bold text-[#F8F8FC] mb-4">Contact Us</h2>
            <div className="space-y-3">
              <div className="flex items-center gap-3 p-4 rounded-xl border border-[#222230] bg-[#111118]">
                <Mail className="w-5 h-5 text-orange-400 flex-shrink-0" />
                <div>
                  <p className="text-xs text-[#52526B]">Email</p>
                  <a href="mailto:support@leadlock.org" className="text-sm text-orange-400 hover:text-orange-300 transition-colors">
                    support@leadlock.org
                  </a>
                </div>
              </div>

              <div className="flex items-center gap-3 p-4 rounded-xl border border-[#222230] bg-[#111118]">
                <MapPin className="w-5 h-5 text-orange-400 flex-shrink-0" />
                <div>
                  <p className="text-xs text-[#52526B]">Address</p>
                  {/* TODO: Replace with actual registered business address */}
                  <p className="text-sm text-[#F8F8FC]">United States</p>
                </div>
              </div>

              <div className="flex items-center gap-3 p-4 rounded-xl border border-[#222230] bg-[#111118]">
                <ExternalLink className="w-5 h-5 text-orange-400 flex-shrink-0" />
                <div>
                  <p className="text-xs text-[#52526B]">Book a Call</p>
                  <a
                    href="https://cal.com/aleksandar-perak-b1yxds/30min"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm text-orange-400 hover:text-orange-300 transition-colors"
                  >
                    Schedule a 30-minute demo
                  </a>
                </div>
              </div>
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
