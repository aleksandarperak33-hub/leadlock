import { Link } from 'react-router-dom';
import { Zap, ArrowLeft, Mail, MapPin, ExternalLink, Send } from 'lucide-react';

export default function Contact() {
  const year = new Date().getFullYear();

  const handleSubmit = (e) => {
    e.preventDefault();
    const form = e.target;
    const name = form.elements.name.value;
    const email = form.elements.email.value;
    const message = form.elements.message.value;
    const subject = `Contact from ${name}`;
    const body = `Name: ${name}\nEmail: ${email}\n\n${message}`;
    window.location.href = `mailto:support@leadlock.org?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
  };

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
          Contact Us
        </h1>
        <p className="text-sm text-[#52526B] mb-12">Get in touch with the LeadLock team</p>

        <div className="grid md:grid-cols-2 gap-12">
          {/* Contact Info */}
          <div className="space-y-4">
            <h2 className="text-lg font-bold text-[#F8F8FC] mb-4">Reach Out</h2>

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
                <p className="text-xs text-[#52526B]">Book a Demo</p>
                <a
                  href="https://cal.com/aleksandar-perak-b1yxds/30min"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm text-orange-400 hover:text-orange-300 transition-colors"
                >
                  Schedule a 30-minute call
                </a>
              </div>
            </div>
          </div>

          {/* Contact Form */}
          <div>
            <h2 className="text-lg font-bold text-[#F8F8FC] mb-4">Send a Message</h2>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label htmlFor="name" className="block text-xs font-medium text-[#A1A1BC] mb-1.5">
                  Name
                </label>
                <input
                  id="name"
                  name="name"
                  type="text"
                  required
                  className="w-full px-4 py-2.5 rounded-xl bg-[#111118] border border-[#222230] text-sm text-[#F8F8FC] placeholder-[#52526B] focus:outline-none focus:border-orange-500/50 transition-colors"
                  placeholder="Your name"
                />
              </div>
              <div>
                <label htmlFor="email" className="block text-xs font-medium text-[#A1A1BC] mb-1.5">
                  Email
                </label>
                <input
                  id="email"
                  name="email"
                  type="email"
                  required
                  className="w-full px-4 py-2.5 rounded-xl bg-[#111118] border border-[#222230] text-sm text-[#F8F8FC] placeholder-[#52526B] focus:outline-none focus:border-orange-500/50 transition-colors"
                  placeholder="you@company.com"
                />
              </div>
              <div>
                <label htmlFor="message" className="block text-xs font-medium text-[#A1A1BC] mb-1.5">
                  Message
                </label>
                <textarea
                  id="message"
                  name="message"
                  rows={4}
                  required
                  className="w-full px-4 py-2.5 rounded-xl bg-[#111118] border border-[#222230] text-sm text-[#F8F8FC] placeholder-[#52526B] focus:outline-none focus:border-orange-500/50 transition-colors resize-none"
                  placeholder="How can we help?"
                />
              </div>
              <button
                type="submit"
                className="w-full px-6 py-3 rounded-xl bg-gradient-to-r from-orange-500 to-orange-600 text-white text-sm font-semibold hover:from-orange-600 hover:to-orange-700 transition-all inline-flex items-center justify-center gap-2"
              >
                <Send className="w-4 h-4" /> Send Message
              </button>
              <p className="text-xs text-[#52526B] text-center">
                Opens your email client with a pre-filled message.
              </p>
            </form>
          </div>
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
