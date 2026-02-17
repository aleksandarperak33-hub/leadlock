import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, useInView, AnimatePresence } from 'framer-motion';
import {
  Zap, MessageSquare, Clock, Shield, Calendar, BarChart3,
  CheckCircle2, ChevronDown, ChevronRight, ArrowRight, Star,
  Phone, Bot, Users, TrendingUp, Lock, Globe, Headphones,
  Menu, X,
} from 'lucide-react';

// ─── Animation Helpers ──────────────────────────────────────────────────────

function FadeUp({ children, delay = 0, className = '' }) {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: '-60px' });
  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, y: 24 }}
      animate={inView ? { opacity: 1, y: 0 } : {}}
      transition={{ duration: 0.5, delay, ease: [0.25, 0.46, 0.45, 0.94] }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

function CountUp({ target, suffix = '', duration = 2000 }) {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true });
  const [count, setCount] = useState(0);

  useEffect(() => {
    if (!inView) return;
    const start = performance.now();
    const step = (now) => {
      const progress = Math.min((now - start) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setCount(Math.round(target * eased));
      if (progress < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }, [inView, target, duration]);

  return <span ref={ref}>{count}{suffix}</span>;
}

// ─── SMS Mockup ─────────────────────────────────────────────────────────────

const SMS_MESSAGES = [
  { from: 'lead', text: "Hi, I need my AC looked at. It's blowing warm air.", delay: 0 },
  { from: 'bot', text: "Hi Sarah! This is LeadLock AI for Apex HVAC. Sorry to hear about your AC! We can help. Is it a central unit or mini-split?", delay: 1500 },
  { from: 'lead', text: "Central. It's a Carrier, maybe 8 years old.", delay: 3500 },
  { from: 'bot', text: "Got it - Carrier central unit, ~8 yrs. We have a tech available tomorrow 9-11 AM or Thursday 2-4 PM. Which works better?", delay: 5000 },
  { from: 'lead', text: "Tomorrow morning works!", delay: 7000 },
  { from: 'bot', text: "Booked! Mike will be there tomorrow 9-11 AM. You'll get a confirmation text shortly. Reply STOP to opt out.", delay: 8500 },
];

function SMSMockup() {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: '-100px' });
  const [visibleCount, setVisibleCount] = useState(0);
  const [showTyping, setShowTyping] = useState(false);

  useEffect(() => {
    if (!inView) return;
    const timers = [];
    SMS_MESSAGES.forEach((msg, i) => {
      if (i > 0 && msg.from === 'bot') {
        timers.push(setTimeout(() => setShowTyping(true), msg.delay - 800));
      }
      timers.push(setTimeout(() => {
        setShowTyping(false);
        setVisibleCount(i + 1);
      }, msg.delay));
    });
    return () => timers.forEach(clearTimeout);
  }, [inView]);

  return (
    <div ref={ref} className="w-full max-w-[340px] mx-auto">
      <div className="rounded-[24px] bg-[#111118] border border-[#222230] p-1 shadow-2xl shadow-black/40">
        {/* Phone top bar */}
        <div className="flex items-center justify-between px-4 py-2">
          <span className="text-[11px] text-[#A1A1BC]">9:41</span>
          <div className="w-20 h-5 rounded-full bg-[#1A1A24]" />
          <div className="flex gap-1">
            <div className="w-4 h-2 rounded-sm bg-[#A1A1BC]/30" />
          </div>
        </div>

        {/* Chat header */}
        <div className="flex items-center gap-2 px-4 py-2 border-b border-[#222230]">
          <div className="w-8 h-8 rounded-full bg-gradient-to-br from-orange-500 to-orange-600 flex items-center justify-center">
            <Zap className="w-4 h-4 text-white" />
          </div>
          <div>
            <p className="text-xs font-semibold text-[#F8F8FC]">Apex HVAC</p>
            <p className="text-[10px] text-emerald-400">AI Assistant</p>
          </div>
        </div>

        {/* Messages */}
        <div className="h-[380px] overflow-hidden px-3 py-3 space-y-2.5">
          {SMS_MESSAGES.slice(0, visibleCount).map((msg, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 10, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              transition={{ duration: 0.3 }}
              className={`flex ${msg.from === 'lead' ? 'justify-end' : 'justify-start'}`}
            >
              <div className={`max-w-[80%] px-3.5 py-2 rounded-2xl text-[13px] leading-relaxed ${
                msg.from === 'lead'
                  ? 'bg-blue-500 text-white rounded-br-md'
                  : 'bg-[#1A1A24] text-[#F8F8FC] rounded-bl-md border border-[#222230]'
              }`}>
                {msg.text}
              </div>
            </motion.div>
          ))}

          {showTyping && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="flex justify-start"
            >
              <div className="px-4 py-2.5 rounded-2xl rounded-bl-md bg-[#1A1A24] border border-[#222230] flex gap-1.5">
                <span className="w-2 h-2 rounded-full bg-[#A1A1BC] typing-dot" />
                <span className="w-2 h-2 rounded-full bg-[#A1A1BC] typing-dot" />
                <span className="w-2 h-2 rounded-full bg-[#A1A1BC] typing-dot" />
              </div>
            </motion.div>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Section Components ─────────────────────────────────────────────────────

const PRICING_TIERS = [
  {
    name: 'Starter',
    price: 497,
    badge: null,
    features: [
      'Up to 200 leads/month',
      'Sub-60s response time',
      '1 CRM integration',
      '3-step follow-up sequences',
      'Standard TCPA compliance',
      'Email support',
    ],
  },
  {
    name: 'Professional',
    price: 997,
    badge: 'MOST POPULAR',
    features: [
      'Unlimited leads',
      'Sub-60s response time',
      'All CRM integrations',
      '5-step advanced sequences',
      'Full compliance (all states)',
      'Priority support',
      'Priority AI conversations',
      'Team dashboard (up to 5 users)',
    ],
  },
  {
    name: 'Enterprise',
    price: 3500,
    badge: null,
    features: [
      'Unlimited leads',
      'Sub-30s response time',
      'All + custom integrations',
      'Custom sequences',
      'Full compliance + audit logs',
      'Dedicated account manager',
      'Unlimited team members',
      'White-label branding',
      'Custom AI persona',
    ],
  },
];

const FAQ_ITEMS = [
  {
    q: 'How fast does LeadLock actually respond?',
    a: 'Our median response time is 8 seconds. Every lead gets a personalized SMS within 60 seconds, guaranteed. The AI qualification conversation starts immediately.',
  },
  {
    q: 'Will my customers know they\'re talking to AI?',
    a: 'We comply with California SB 1001 and disclose AI involvement. However, our conversations are so natural that most leads engage without hesitation. Contractors report 3x higher booking rates.',
  },
  {
    q: 'What CRMs do you integrate with?',
    a: 'ServiceTitan, Housecall Pro, Jobber, GoHighLevel, and Google Sheets as a universal fallback. Custom integrations available on Agency plans.',
  },
  {
    q: 'What about TCPA compliance?',
    a: 'Compliance is baked into every message. We enforce consent tracking, opt-out processing, quiet hours (state-specific), and maintain 5-year consent records. Our system has never had a TCPA violation.',
  },
  {
    q: 'How does the AI qualify leads?',
    a: 'Our 4-agent pipeline handles intake, qualification (in 4 messages or less), booking, and follow-up. It identifies service type, urgency, and availability, then books directly into your calendar.',
  },
  {
    q: 'What happens if a lead has an emergency?',
    a: 'Emergency keywords (gas leak, flooding, no heat in winter) trigger immediate priority routing. These bypass quiet hours under the life safety exception and get flagged for your on-call team.',
  },
  {
    q: 'Can I see what the AI is saying to my customers?',
    a: 'Yes. Every conversation is logged in your dashboard with full transparency. You can review conversations, see AI decisions, and monitor quality scores in real-time.',
  },
  {
    q: 'What if I want to cancel?',
    a: 'Cancel anytime, no contracts. Your data exports cleanly (CSV) and we retain compliance records for the required 5-year period.',
  },
];

const FEATURES = [
  {
    icon: Zap,
    title: 'Sub-60s Response',
    desc: 'Every lead gets a personalized SMS in under 60 seconds. Our median is 8 seconds.',
    size: 'large',
  },
  {
    icon: Bot,
    title: 'AI Qualification',
    desc: 'Intelligent 4-message conversation that identifies service needs, urgency, and books appointments.',
    size: 'large',
  },
  {
    icon: Calendar,
    title: 'Auto-Booking',
    desc: 'Books directly into ServiceTitan, Housecall Pro, Jobber, or GoHighLevel. No double-booking.',
    size: 'medium',
  },
  {
    icon: Shield,
    title: 'TCPA Compliance',
    desc: 'Every message audited. Consent tracking, opt-out, quiet hours, state-specific rules.',
    size: 'medium',
  },
  {
    icon: TrendingUp,
    title: 'Follow-Up Sequences',
    desc: 'Automated nurture for cold leads. Up to 5 touchpoints that respect compliance limits.',
    size: 'medium',
  },
];

const TESTIMONIALS = [
  {
    name: 'Mike R.',
    role: 'Owner, Apex HVAC',
    quote: 'We went from losing 40% of after-hours leads to booking 3x more jobs. LeadLock pays for itself in the first week.',
    metric: '3x more bookings',
    stars: 5,
  },
  {
    name: 'Sarah T.',
    role: 'GM, ProPlumb Solutions',
    quote: 'The speed is unreal. Customers think they\'re talking to our best dispatcher. We\'ve cut our response time from 4 hours to 8 seconds.',
    metric: '8s avg response',
    stars: 5,
  },
  {
    name: 'Carlos D.',
    role: 'Founder, Summit Roofing',
    quote: 'TCPA compliance was a nightmare before LeadLock. Now it\'s handled automatically. Zero violations in 6 months.',
    metric: '0 TCPA violations',
    stars: 5,
  },
];

function FAQItem({ item, isOpen, onToggle }) {
  return (
    <div className={`border rounded-xl transition-all duration-300 ${isOpen ? 'ld-faq-open' : 'border-[#222230]'}`}>
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between px-6 py-4 text-left"
      >
        <span className="text-[15px] font-medium text-[#F8F8FC] pr-4">{item.q}</span>
        <ChevronDown className={`w-5 h-5 text-[#52526B] flex-shrink-0 transition-transform duration-300 ${isOpen ? 'rotate-180' : ''}`} />
      </button>
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.3 }}
            className="overflow-hidden"
          >
            <p className="px-6 pb-4 text-sm leading-relaxed text-[#A1A1BC]">{item.a}</p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ─── Main Landing Component ─────────────────────────────────────────────────

export default function Landing() {
  const navigate = useNavigate();
  const [scrolled, setScrolled] = useState(false);
  const [openFaq, setOpenFaq] = useState(null);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 20);
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  const scrollTo = (id) => {
    setMobileMenuOpen(false);
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' });
  };

  return (
    <div className="landing-dark min-h-screen">
      {/* ═══ 1. STICKY NAV ═══ */}
      <nav className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${
        scrolled ? 'ld-nav-glass' : 'bg-transparent'
      }`}>
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            {/* Logo */}
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-orange-500 to-orange-600 flex items-center justify-center shadow-lg shadow-orange-500/25">
                <Zap className="w-4 h-4 text-white" strokeWidth={2.5} />
              </div>
              <span className="text-lg font-bold tracking-tight text-[#F8F8FC]">
                Lead<span className="text-orange-500">Lock</span>
              </span>
            </div>

            {/* Desktop Nav */}
            <div className="hidden md:flex items-center gap-8">
              {['How It Works', 'Features', 'Pricing', 'FAQ'].map(label => (
                <button
                  key={label}
                  onClick={() => scrollTo(label.toLowerCase().replace(/\s/g, '-'))}
                  className="text-sm text-[#A1A1BC] hover:text-[#F8F8FC] transition-colors"
                >
                  {label}
                </button>
              ))}
            </div>

            {/* CTAs */}
            <div className="hidden md:flex items-center gap-3">
              <button
                onClick={() => navigate('/login')}
                className="px-4 py-2 text-sm text-[#A1A1BC] hover:text-[#F8F8FC] transition-colors"
              >
                Login
              </button>
              <button
                onClick={() => navigate('/signup')}
                className="ld-btn-primary px-5 py-2 text-sm"
              >
                Get Started
              </button>
            </div>

            {/* Mobile menu toggle */}
            <button
              className="md:hidden text-[#A1A1BC]"
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            >
              {mobileMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
            </button>
          </div>
        </div>

        {/* Mobile menu */}
        <AnimatePresence>
          {mobileMenuOpen && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              className="md:hidden bg-[#111118] border-t border-[#222230]"
            >
              <div className="px-4 py-4 space-y-3">
                {['How It Works', 'Features', 'Pricing', 'FAQ'].map(label => (
                  <button
                    key={label}
                    onClick={() => scrollTo(label.toLowerCase().replace(/\s/g, '-'))}
                    className="block w-full text-left text-sm text-[#A1A1BC] hover:text-[#F8F8FC] py-2"
                  >
                    {label}
                  </button>
                ))}
                <div className="flex gap-3 pt-2">
                  <button onClick={() => navigate('/login')} className="ld-btn-secondary px-4 py-2 text-sm flex-1">Login</button>
                  <button onClick={() => navigate('/signup')} className="ld-btn-primary px-4 py-2 text-sm flex-1">Get Started</button>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </nav>

      {/* ═══ 2. HERO ═══ */}
      <section className="ld-gradient-hero min-h-screen flex items-center pt-16">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20 lg:py-0">
          <div className="grid lg:grid-cols-2 gap-12 lg:gap-16 items-center">
            {/* Left — Copy */}
            <div>
              <FadeUp>
                <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-orange-500/10 border border-orange-500/20 mb-6">
                  <span className="w-2 h-2 rounded-full bg-orange-500 animate-pulse" />
                  <span className="text-xs font-medium text-orange-400">AI-Powered Speed-to-Lead</span>
                </div>
              </FadeUp>

              <FadeUp delay={0.1}>
                <h1 className="text-4xl sm:text-5xl lg:text-6xl font-black tracking-[-0.04em] leading-[1.05] mb-6" style={{ fontFamily: 'Inter, sans-serif' }}>
                  Every lead answered
                  <br />
                  <span className="bg-gradient-to-r from-orange-500 to-orange-400 bg-clip-text text-transparent">in under 60 seconds</span>
                </h1>
              </FadeUp>

              <FadeUp delay={0.2}>
                <p className="text-lg text-[#A1A1BC] max-w-lg mb-8 leading-relaxed">
                  AI that responds to leads, qualifies them, and books appointments
                  directly into your CRM. Built for home services contractors who
                  refuse to lose another lead to slow follow-up.
                </p>
              </FadeUp>

              <FadeUp delay={0.3}>
                <div className="flex flex-col sm:flex-row gap-3">
                  <button
                    onClick={() => navigate('/signup')}
                    className="ld-btn-primary px-7 py-3.5 text-base inline-flex items-center justify-center gap-2"
                  >
                    Get Started <ArrowRight className="w-5 h-5" />
                  </button>
                  <button
                    onClick={() => scrollTo('how-it-works')}
                    className="ld-btn-secondary px-7 py-3.5 text-base inline-flex items-center justify-center gap-2"
                  >
                    See How It Works
                  </button>
                </div>
              </FadeUp>
            </div>

            {/* Right — SMS Mockup */}
            <FadeUp delay={0.3} className="flex justify-center lg:justify-end">
              <SMSMockup />
            </FadeUp>
          </div>
        </div>
      </section>

      {/* ═══ 3. SOCIAL PROOF BAR ═══ */}
      <section className="border-y border-[#222230] bg-[#111118]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-8">
            {[
              { value: 47, suffix: 's', label: 'Median Response Time' },
              { value: 3, suffix: 'x', label: 'More Bookings' },
              { value: 98, suffix: '.7%', label: 'Compliance Rate' },
              { value: 500, suffix: '+', label: 'Contractors Served' },
            ].map((stat, i) => (
              <FadeUp key={i} delay={i * 0.1} className="text-center">
                <div className="text-3xl sm:text-4xl font-black tracking-tight text-[#F8F8FC]" style={{ fontFamily: 'Inter, sans-serif' }}>
                  <CountUp target={stat.value} />{stat.suffix}
                </div>
                <p className="text-sm text-[#52526B] mt-1">{stat.label}</p>
              </FadeUp>
            ))}
          </div>
        </div>
      </section>

      {/* ═══ SAVINGS HOOK ═══ */}
      <section className="py-20 lg:py-24">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
          <FadeUp>
            <div className="relative rounded-2xl border border-orange-500/20 bg-gradient-to-br from-orange-500/[0.08] to-transparent p-10 sm:p-14 text-center overflow-hidden">
              <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,rgba(249,115,22,0.08),transparent_60%)]" />
              <div className="relative z-10">
                <p className="text-xs font-bold uppercase tracking-widest text-orange-400 mb-4">Average contractor savings</p>
                <div className="text-5xl sm:text-6xl lg:text-7xl font-black tracking-[-0.04em] text-[#F8F8FC] mb-4" style={{ fontFamily: 'Inter, sans-serif' }}>
                  $<CountUp target={4200} /><span className="text-[#52526B]">/mo</span>
                </div>
                <p className="text-base sm:text-lg text-[#A1A1BC] max-w-2xl mx-auto leading-relaxed">
                  in recovered revenue from leads that would have gone cold.
                  The average contractor loses <span className="text-orange-400 font-semibold">$50,000+ per year</span> to slow follow-up.
                </p>
              </div>
            </div>
          </FadeUp>
        </div>
      </section>

      {/* ═══ 4. THE PROBLEM ═══ */}
      <section className="py-24 lg:py-32">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <FadeUp className="text-center mb-16">
            <h2 className="text-3xl sm:text-4xl font-black tracking-[-0.03em] mb-4" style={{ fontFamily: 'Inter, sans-serif' }}>
              Slow follow-up is <span className="text-red-400">killing your revenue</span>
            </h2>
            <p className="text-[#A1A1BC] max-w-2xl mx-auto">
              The data is clear: respond in under 60 seconds and you're 21x more likely to book.
              Most contractors take 4+ hours. That's money left on the table.
            </p>
          </FadeUp>

          <div className="grid md:grid-cols-2 gap-8 max-w-4xl mx-auto">
            {/* Before */}
            <FadeUp>
              <div className="ld-card p-8 border-red-500/20 hover:border-red-500/30">
                <div className="text-xs font-bold uppercase tracking-wider text-red-400 mb-4">Without LeadLock</div>
                <ul className="space-y-3">
                  {[
                    '4+ hour average response time',
                    '40% of leads never get a callback',
                    'Missed after-hours leads (50% of volume)',
                    'No compliance tracking',
                    'Manual scheduling = double bookings',
                  ].map((item, i) => (
                    <li key={i} className="flex items-start gap-3 text-sm text-[#A1A1BC]">
                      <X className="w-4 h-4 text-red-400 mt-0.5 flex-shrink-0" />
                      {item}
                    </li>
                  ))}
                </ul>
              </div>
            </FadeUp>

            {/* After */}
            <FadeUp delay={0.1}>
              <div className="ld-card p-8 border-emerald-500/20 hover:border-emerald-500/30">
                <div className="text-xs font-bold uppercase tracking-wider text-emerald-400 mb-4">With LeadLock</div>
                <ul className="space-y-3">
                  {[
                    '8-second median response time',
                    '100% of leads get an instant reply',
                    '24/7 coverage including holidays',
                    'TCPA compliance built into every message',
                    'Auto-booking into your CRM',
                  ].map((item, i) => (
                    <li key={i} className="flex items-start gap-3 text-sm text-[#A1A1BC]">
                      <CheckCircle2 className="w-4 h-4 text-emerald-400 mt-0.5 flex-shrink-0" />
                      {item}
                    </li>
                  ))}
                </ul>
              </div>
            </FadeUp>
          </div>
        </div>
      </section>

      {/* ═══ 5. HOW IT WORKS ═══ */}
      <section id="how-it-works" className="py-24 lg:py-32 ld-gradient-section">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <FadeUp className="text-center mb-16">
            <h2 className="text-3xl sm:text-4xl font-black tracking-[-0.03em] mb-4" style={{ fontFamily: 'Inter, sans-serif' }}>
              From lead to booked in <span className="text-orange-500">4 steps</span>
            </h2>
            <p className="text-[#A1A1BC] max-w-2xl mx-auto">
              Our AI agent pipeline handles the entire lead lifecycle automatically.
            </p>
          </FadeUp>

          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-6">
            {[
              { step: 1, icon: MessageSquare, title: 'Instant Response', desc: 'Lead comes in via form, call, or text. AI responds in under 10 seconds with a personalized message.', color: 'orange' },
              { step: 2, icon: Bot, title: 'AI Qualification', desc: 'Conversational AI identifies service type, urgency, timeline, and budget in 4 messages or less.', color: 'blue' },
              { step: 3, icon: Calendar, title: 'Auto-Booking', desc: 'Checks your real-time availability and books the appointment directly into your CRM.', color: 'emerald' },
              { step: 4, icon: TrendingUp, title: 'Follow-Up', desc: 'Cold leads get automated nurture sequences. Warm leads get priority routing to your team.', color: 'amber' },
            ].map((item, i) => (
              <FadeUp key={i} delay={i * 0.1}>
                <div className="ld-card p-6 h-full relative overflow-hidden">
                  <div className="absolute top-0 right-0 text-[80px] font-black text-[#1A1A24] leading-none pr-3 select-none" style={{ fontFamily: 'Inter, sans-serif' }}>
                    {item.step}
                  </div>
                  <div className={`w-10 h-10 rounded-xl flex items-center justify-center mb-4 ${
                    item.color === 'orange' ? 'bg-orange-500/10 text-orange-400' :
                    item.color === 'blue' ? 'bg-blue-500/10 text-blue-400' :
                    item.color === 'emerald' ? 'bg-emerald-500/10 text-emerald-400' :
                    'bg-orange-500/10 text-amber-400'
                  }`}>
                    <item.icon className="w-5 h-5" />
                  </div>
                  <h3 className="text-base font-bold text-[#F8F8FC] mb-2 relative z-10">{item.title}</h3>
                  <p className="text-sm text-[#A1A1BC] leading-relaxed relative z-10">{item.desc}</p>
                </div>
              </FadeUp>
            ))}
          </div>
        </div>
      </section>

      {/* ═══ 6. FEATURES BENTO GRID ═══ */}
      <section id="features" className="py-24 lg:py-32">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <FadeUp className="text-center mb-16">
            <h2 className="text-3xl sm:text-4xl font-black tracking-[-0.03em] mb-4" style={{ fontFamily: 'Inter, sans-serif' }}>
              Built for contractors who <span className="text-orange-500">demand more</span>
            </h2>
          </FadeUp>

          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
            {FEATURES.map((feat, i) => (
              <FadeUp key={i} delay={i * 0.08} className={feat.size === 'large' ? 'lg:col-span-1' : ''}>
                <div className="ld-card p-6 h-full">
                  <div className="w-10 h-10 rounded-xl bg-orange-500/10 flex items-center justify-center mb-4">
                    <feat.icon className="w-5 h-5 text-orange-400" />
                  </div>
                  <h3 className="text-base font-bold text-[#F8F8FC] mb-2">{feat.title}</h3>
                  <p className="text-sm text-[#A1A1BC] leading-relaxed">{feat.desc}</p>
                </div>
              </FadeUp>
            ))}
          </div>
        </div>
      </section>

      {/* ═══ 7. COMPLIANCE & TRUST ═══ */}
      <section className="py-24 lg:py-32 ld-gradient-section">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <FadeUp className="text-center mb-16">
            <h2 className="text-3xl sm:text-4xl font-black tracking-[-0.03em] mb-4" style={{ fontFamily: 'Inter, sans-serif' }}>
              Compliance is <span className="text-emerald-400">non-negotiable</span>
            </h2>
            <p className="text-[#A1A1BC] max-w-2xl mx-auto">
              TCPA violations carry $500-$1,500 per message with no cap. We make sure you never have to worry.
            </p>
          </FadeUp>

          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6 max-w-5xl mx-auto">
            {[
              { icon: Shield, title: 'TCPA Compliant', desc: 'Every message is checked against TCPA rules before sending. Consent tracking, opt-out processing, 5-year records.' },
              { icon: Globe, title: 'State-Specific Rules', desc: 'Automatic enforcement of Texas SB 140, Florida FTSA, California SB 1001, and all other state-specific regulations.' },
              { icon: Lock, title: 'Data Security', desc: 'SOC 2 aligned infrastructure. PII masking in logs. Encrypted data at rest and in transit.' },
            ].map((item, i) => (
              <FadeUp key={i} delay={i * 0.1}>
                <div className="ld-card p-6 h-full">
                  <div className="w-10 h-10 rounded-xl bg-emerald-500/10 flex items-center justify-center mb-4">
                    <item.icon className="w-5 h-5 text-emerald-400" />
                  </div>
                  <h3 className="text-base font-bold text-[#F8F8FC] mb-2">{item.title}</h3>
                  <p className="text-sm text-[#A1A1BC] leading-relaxed">{item.desc}</p>
                </div>
              </FadeUp>
            ))}
          </div>
        </div>
      </section>

      {/* ═══ 8. TESTIMONIALS ═══ */}
      <section className="py-24 lg:py-32">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <FadeUp className="text-center mb-16">
            <h2 className="text-3xl sm:text-4xl font-black tracking-[-0.03em] mb-4" style={{ fontFamily: 'Inter, sans-serif' }}>
              Trusted by <span className="text-orange-500">top contractors</span>
            </h2>
          </FadeUp>

          <div className="grid md:grid-cols-3 gap-6 max-w-5xl mx-auto">
            {TESTIMONIALS.map((t, i) => (
              <FadeUp key={i} delay={i * 0.1}>
                <div className="ld-card p-6 h-full flex flex-col">
                  <div className="flex gap-0.5 mb-4">
                    {Array.from({ length: t.stars }).map((_, j) => (
                      <Star key={j} className="w-4 h-4 fill-orange-500 text-orange-500" />
                    ))}
                  </div>
                  <p className="text-sm text-[#A1A1BC] leading-relaxed mb-6 flex-1">"{t.quote}"</p>
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-semibold text-[#F8F8FC]">{t.name}</p>
                      <p className="text-xs text-[#52526B]">{t.role}</p>
                    </div>
                    <div className="px-3 py-1 rounded-full bg-orange-500/10 text-xs font-semibold text-orange-400">
                      {t.metric}
                    </div>
                  </div>
                </div>
              </FadeUp>
            ))}
          </div>
        </div>
      </section>

      {/* ═══ 9. PRICING ═══ */}
      <section id="pricing" className="py-24 lg:py-32 ld-gradient-section">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <FadeUp className="text-center mb-16">
            <h2 className="text-3xl sm:text-4xl font-black tracking-[-0.03em] mb-4" style={{ fontFamily: 'Inter, sans-serif' }}>
              Simple, transparent <span className="text-orange-500">pricing</span>
            </h2>
            <p className="text-[#A1A1BC] max-w-xl mx-auto">
              No hidden fees. No per-lead charges. Every plan includes AI conversations, compliance, and CRM integration.
            </p>
          </FadeUp>

          <div className="grid md:grid-cols-3 gap-6 max-w-5xl mx-auto">
            {PRICING_TIERS.map((tier, i) => (
              <FadeUp key={i} delay={i * 0.1}>
                <div className={`ld-card p-8 h-full flex flex-col relative ${
                  tier.badge ? 'ld-pricing-popular' : ''
                }`}>
                  {tier.badge && (
                    <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-4 py-1 rounded-full bg-gradient-to-r from-orange-500 to-orange-400 text-xs font-bold text-white">
                      {tier.badge}
                    </div>
                  )}
                  <h3 className="text-lg font-bold text-[#F8F8FC] mb-2">{tier.name}</h3>
                  <div className="flex items-baseline gap-1 mb-6">
                    <span className="text-4xl font-black text-[#F8F8FC]" style={{ fontFamily: 'Inter, sans-serif' }}>
                      ${tier.price.toLocaleString()}
                    </span>
                    <span className="text-sm text-[#52526B]">/mo</span>
                  </div>
                  <ul className="space-y-3 mb-8 flex-1">
                    {tier.features.map((feat, j) => (
                      <li key={j} className="flex items-start gap-2.5 text-sm text-[#A1A1BC]">
                        <CheckCircle2 className="w-4 h-4 text-orange-400 mt-0.5 flex-shrink-0" />
                        {feat}
                      </li>
                    ))}
                  </ul>
                  <button
                    onClick={() => navigate('/signup')}
                    className={`w-full py-3 rounded-xl text-sm font-semibold transition-all ${
                      tier.badge
                        ? 'ld-btn-primary'
                        : 'ld-btn-secondary'
                    }`}
                  >
                    Get Started
                  </button>
                </div>
              </FadeUp>
            ))}
          </div>
        </div>
      </section>

      {/* ═══ 10. FAQ ═══ */}
      <section id="faq" className="py-24 lg:py-32">
        <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8">
          <FadeUp className="text-center mb-16">
            <h2 className="text-3xl sm:text-4xl font-black tracking-[-0.03em] mb-4" style={{ fontFamily: 'Inter, sans-serif' }}>
              Frequently asked <span className="text-orange-500">questions</span>
            </h2>
          </FadeUp>

          <div className="space-y-3">
            {FAQ_ITEMS.map((item, i) => (
              <FadeUp key={i} delay={i * 0.05}>
                <FAQItem
                  item={item}
                  isOpen={openFaq === i}
                  onToggle={() => setOpenFaq(openFaq === i ? null : i)}
                />
              </FadeUp>
            ))}
          </div>
        </div>
      </section>

      {/* ═══ 11. FINAL CTA ═══ */}
      <section className="py-24 lg:py-32">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
          <FadeUp>
            <div className="ld-gradient-cta rounded-3xl p-12 sm:p-16 text-center border border-orange-500/10">
              <h2 className="text-3xl sm:text-4xl font-black tracking-[-0.03em] mb-4 text-[#F8F8FC]" style={{ fontFamily: 'Inter, sans-serif' }}>
                Stop losing leads to slow follow-up
              </h2>
              <p className="text-lg text-[#A1A1BC] mb-8 max-w-xl mx-auto">
                Join 500+ contractors who book more jobs with AI-powered speed-to-lead.
              </p>
              <button
                onClick={() => navigate('/signup')}
                className="ld-btn-primary px-8 py-4 text-base inline-flex items-center gap-2"
              >
                Get Started <ArrowRight className="w-5 h-5" />
              </button>
            </div>
          </FadeUp>
        </div>
      </section>

      {/* ═══ 12. FOOTER ═══ */}
      <footer className="border-t border-[#222230] py-12">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-8 mb-12">
            {/* Brand */}
            <div>
              <div className="flex items-center gap-2.5 mb-4">
                <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-orange-500 to-orange-600 flex items-center justify-center">
                  <Zap className="w-4 h-4 text-white" strokeWidth={2.5} />
                </div>
                <span className="text-lg font-bold text-[#F8F8FC]">
                  Lead<span className="text-orange-500">Lock</span>
                </span>
              </div>
              <p className="text-sm text-[#52526B] leading-relaxed">
                AI-powered speed-to-lead platform for home services contractors.
              </p>
            </div>

            {/* Product */}
            <div>
              <h4 className="text-xs font-bold uppercase tracking-wider text-[#52526B] mb-4">Product</h4>
              <ul className="space-y-2">
                {['Features', 'Pricing', 'Integrations', 'API'].map(item => (
                  <li key={item}>
                    <button onClick={() => scrollTo(item.toLowerCase())} className="text-sm text-[#A1A1BC] hover:text-[#F8F8FC] transition-colors">
                      {item}
                    </button>
                  </li>
                ))}
              </ul>
            </div>

            {/* Company */}
            <div>
              <h4 className="text-xs font-bold uppercase tracking-wider text-[#52526B] mb-4">Company</h4>
              <ul className="space-y-2">
                {['About', 'Blog', 'Careers', 'Contact'].map(item => (
                  <li key={item}>
                    <span className="text-sm text-[#A1A1BC] hover:text-[#F8F8FC] transition-colors cursor-pointer">
                      {item}
                    </span>
                  </li>
                ))}
              </ul>
            </div>

            {/* Legal */}
            <div>
              <h4 className="text-xs font-bold uppercase tracking-wider text-[#52526B] mb-4">Legal</h4>
              <ul className="space-y-2">
                {['Privacy Policy', 'Terms of Service', 'TCPA Compliance', 'Security'].map(item => (
                  <li key={item}>
                    <span className="text-sm text-[#A1A1BC] hover:text-[#F8F8FC] transition-colors cursor-pointer">
                      {item}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          </div>

          <div className="border-t border-[#222230] pt-8 flex flex-col sm:flex-row items-center justify-between gap-4">
            <p className="text-xs text-[#52526B]">
              &copy; {new Date().getFullYear()} LeadLock. All rights reserved.
            </p>
            <p className="text-xs text-[#52526B]">
              Built with compliance in mind. TCPA, FTSA, SB 1001 compliant.
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}
