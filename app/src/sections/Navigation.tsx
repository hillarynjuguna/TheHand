import { useEffect, useRef, useState } from 'react';
import gsap from 'gsap';

const NAV_LINKS = [
  { label: 'How It Works', href: '#how-it-works' },
  { label: 'Setup', href: '#setup' },
  { label: 'GitHub', href: 'https://github.com/ggml-org/whisper.cpp', external: true },
];

export default function Navigation() {
  const navRef = useRef<HTMLElement>(null);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    if (navRef.current) {
      gsap.from(navRef.current, {
        y: -20,
        opacity: 0,
        duration: 0.8,
        delay: 0.5,
        ease: 'power3.out',
      });
    }
  }, []);

  const scrollTo = (href: string) => {
    setMobileOpen(false);
    if (href.startsWith('#')) {
      const el = document.querySelector(href);
      if (el) {
        el.scrollIntoView({ behavior: 'smooth' });
      }
    }
  };

  return (
    <nav
      ref={navRef}
      className="fixed top-0 left-0 right-0 z-50"
      style={{
        background: 'rgba(245, 240, 232, 0.85)',
        backdropFilter: 'blur(20px)',
        WebkitBackdropFilter: 'blur(20px)',
      }}
    >
      <div className="max-w-[1200px] mx-auto flex items-center justify-between h-16 px-6">
        <a
          href="#"
          className="text-lg font-bold tracking-tight"
          style={{ fontFamily: "'Space Grotesk', sans-serif", color: '#1A1A1A', letterSpacing: '-0.02em' }}
        >
          transcribe.local
        </a>

        {/* Desktop nav */}
        <div className="hidden md:flex items-center gap-8">
          {NAV_LINKS.map((link) => (
            <a
              key={link.label}
              href={link.href}
              onClick={(e) => {
                if (!link.external) {
                  e.preventDefault();
                  scrollTo(link.href);
                }
              }}
              target={link.external ? '_blank' : undefined}
              rel={link.external ? 'noopener noreferrer' : undefined}
              className="text-sm font-medium transition-colors duration-300 hover:text-[#C17F59]"
              style={{ color: '#6B6560', fontFamily: "'Inter', sans-serif" }}
            >
              {link.label}
            </a>
          ))}
          <a
            href="#"
            onClick={(e) => {
              e.preventDefault();
              scrollTo('#setup');
            }}
            className="text-sm font-medium px-5 py-2.5 rounded-full transition-colors duration-300 hover:bg-[#C17F59]"
            style={{
              background: '#1A1A1A',
              color: '#F5F0E8',
              fontFamily: "'Inter', sans-serif",
            }}
          >
            Get Started
          </a>
        </div>

        {/* Mobile hamburger */}
        <button
          className="md:hidden flex flex-col gap-1.5 p-2"
          onClick={() => setMobileOpen(!mobileOpen)}
          aria-label="Toggle menu"
        >
          <span
            className="block w-5 h-0.5 transition-transform duration-300"
            style={{
              background: '#1A1A1A',
              transform: mobileOpen ? 'rotate(45deg) translateY(4px)' : 'none',
            }}
          />
          <span
            className="block w-5 h-0.5 transition-opacity duration-300"
            style={{
              background: '#1A1A1A',
              opacity: mobileOpen ? 0 : 1,
            }}
          />
          <span
            className="block w-5 h-0.5 transition-transform duration-300"
            style={{
              background: '#1A1A1A',
              transform: mobileOpen ? 'rotate(-45deg) translateY(-4px)' : 'none',
            }}
          />
        </button>
      </div>

      {/* Mobile menu */}
      {mobileOpen && (
        <div
          className="md:hidden px-6 pb-6 flex flex-col gap-4"
          style={{ background: 'rgba(245, 240, 232, 0.95)' }}
        >
          {NAV_LINKS.map((link) => (
            <a
              key={link.label}
              href={link.href}
              onClick={(e) => {
                if (!link.external) {
                  e.preventDefault();
                  scrollTo(link.href);
                }
              }}
              target={link.external ? '_blank' : undefined}
              rel={link.external ? 'noopener noreferrer' : undefined}
              className="text-sm font-medium"
              style={{ color: '#6B6560', fontFamily: "'Inter', sans-serif" }}
            >
              {link.label}
            </a>
          ))}
          <a
            href="#setup"
            onClick={(e) => {
              e.preventDefault();
              scrollTo('#setup');
            }}
            className="text-sm font-medium px-5 py-2.5 rounded-full text-center"
            style={{
              background: '#1A1A1A',
              color: '#F5F0E8',
              fontFamily: "'Inter', sans-serif",
            }}
          >
            Get Started
          </a>
        </div>
      )}
    </nav>
  );
}
