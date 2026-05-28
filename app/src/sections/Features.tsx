import { useEffect, useRef } from 'react';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';

gsap.registerPlugin(ScrollTrigger);

const FEATURES = [
  {
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      </svg>
    ),
    title: '100% Offline',
    desc: 'Transcription happens locally via Whisper.cpp. Your audio never touches the internet.',
  },
  {
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
      </svg>
    ),
    title: 'Multiple Formats',
    desc: 'Export as plain text, SRT subtitles, VTT web captions, or JSON with word-level timestamps.',
  },
  {
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="4" y="4" width="16" height="16" rx="2" ry="2" />
        <rect x="9" y="9" width="6" height="6" />
        <line x1="9" y1="1" x2="9" y2="4" />
        <line x1="15" y1="1" x2="15" y2="4" />
        <line x1="9" y1="20" x2="9" y2="23" />
        <line x1="15" y1="20" x2="15" y2="23" />
        <line x1="20" y1="9" x2="23" y2="9" />
        <line x1="20" y1="14" x2="23" y2="14" />
        <line x1="1" y1="9" x2="4" y2="9" />
        <line x1="1" y1="14" x2="4" y2="14" />
      </svg>
    ),
    title: 'Model Choices',
    desc: 'From tiny (75MB) for quick notes to large-v3 for maximum accuracy. Pick what fits your hardware.',
  },
  {
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10" />
        <line x1="2" y1="12" x2="22" y2="12" />
        <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
      </svg>
    ),
    title: '99 Languages',
    desc: 'Whisper supports automatic language detection and transcription across 99 languages.',
  },
];

export default function Features() {
  const sectionRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!sectionRef.current) return;

    const cards = sectionRef.current.querySelectorAll('.feature-card');
    cards.forEach((card, i) => {
      gsap.from(card, {
        y: 50,
        opacity: 0,
        duration: 0.8,
        ease: 'power3.out',
        scrollTrigger: {
          trigger: card,
          start: 'top 80%',
          toggleActions: 'play none none none',
        },
        delay: i * 0.1,
      });
    });
  }, []);

  return (
    <section
      ref={sectionRef}
      className="w-full"
      style={{ padding: '120px 0', background: 'rgba(255, 255, 255, 0.4)' }}
    >
      <div className="max-w-[1200px] mx-auto px-6">
        <h2
          style={{
            fontFamily: "'Space Grotesk', sans-serif",
            fontSize: 'clamp(28px, 4vw, 42px)',
            fontWeight: 600,
            letterSpacing: '-0.02em',
            lineHeight: 1.15,
            color: '#1A1A1A',
          }}
        >
          Built for Privacy, Designed for Speed
        </h2>
        <p
          className="mt-4"
          style={{
            fontFamily: "'Inter', sans-serif",
            fontSize: '17px',
            color: '#6B6560',
            maxWidth: '600px',
            lineHeight: 1.6,
          }}
        >
          Everything runs on your device. No subscriptions. No data harvesting. No cloud dependencies.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mt-14">
          {FEATURES.map((feature) => (
            <div
              key={feature.title}
              className="feature-card flex gap-6 p-8 transition-all duration-300"
              style={{
                background: 'rgba(255, 255, 255, 0.8)',
                borderRadius: '16px',
                border: '1px solid rgba(26, 26, 26, 0.06)',
              }}
            >
              <div
                className="flex-shrink-0 w-12 h-12 rounded-full flex items-center justify-center"
                style={{ background: 'rgba(193, 127, 89, 0.1)', color: '#C17F59' }}
              >
                {feature.icon}
              </div>
              <div>
                <h3
                  style={{
                    fontFamily: "'Space Grotesk', sans-serif",
                    fontSize: '18px',
                    fontWeight: 600,
                    color: '#1A1A1A',
                  }}
                >
                  {feature.title}
                </h3>
                <p
                  className="mt-1"
                  style={{
                    fontFamily: "'Inter', sans-serif",
                    fontSize: '14px',
                    color: '#6B6560',
                    lineHeight: 1.6,
                  }}
                >
                  {feature.desc}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
