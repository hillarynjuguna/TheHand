import { useEffect, useRef, useState } from 'react';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';

gsap.registerPlugin(ScrollTrigger);

const STEPS = [
  {
    num: '01',
    title: 'Paste or Upload',
    desc: 'Drop a YouTube link, TikTok URL, or any audio file. We handle the rest — downloading, extracting, and converting.',
  },
  {
    num: '02',
    title: 'AI Transcribes',
    desc: 'Whisper.cpp runs locally on your device. No audio ever leaves your phone. Complete privacy, zero network dependency.',
  },
  {
    num: '03',
    title: 'Get Your Text',
    desc: 'Copy clean transcripts, export as SRT subtitles, or download JSON with timestamps. Your data stays yours.',
  },
];

const SCRAMBLE_CHARS = 'x$#%&*';

function useTextScramble(text: string, trigger: boolean, duration = 800) {
  const [display, setDisplay] = useState(text);
  const frameRef = useRef<number>(0);

  useEffect(() => {
    if (!trigger) return;

    const startTime = performance.now();
    const textLen = text.length;

    const tick = (now: number) => {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);

      let result = '';
      for (let i = 0; i < textLen; i++) {
        if (text[i] === ' ') {
          result += ' ';
        } else if (progress > (i + 1) / textLen) {
          result += text[i];
        } else {
          result += SCRAMBLE_CHARS[Math.floor(Math.random() * SCRAMBLE_CHARS.length)];
        }
      }
      setDisplay(result);

      if (progress < 1) {
        frameRef.current = requestAnimationFrame(tick);
      } else {
        setDisplay(text);
      }
    };

    frameRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frameRef.current);
  }, [trigger, text, duration]);

  return display;
}

export default function HowItWorks() {
  const sectionRef = useRef<HTMLElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const [scrambleTrigger, setScrambleTrigger] = useState(false);

  const headingText = useTextScramble('How It Works', scrambleTrigger, 800);

  useEffect(() => {
    if (!headingRef.current || !sectionRef.current) return;

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            setScrambleTrigger(true);
          }
        });
      },
      { threshold: 0.3 }
    );

    observer.observe(headingRef.current);

    // Animate cards
    const cards = sectionRef.current.querySelectorAll('.hiw-card');
    cards.forEach((card, i) => {
      gsap.from(card, {
        y: 60,
        opacity: 0,
        duration: 0.9,
        ease: 'power3.out',
        scrollTrigger: {
          trigger: card,
          start: 'top 80%',
          toggleActions: 'play none none none',
        },
        delay: i * 0.15,
      });
    });

    return () => {
      observer.disconnect();
    };
  }, []);

  return (
    <section
      id="how-it-works"
      ref={sectionRef}
      className="w-full"
      style={{ padding: '120px 0', background: '#F5F0E8' }}
    >
      <div className="max-w-[1200px] mx-auto px-6">
        <h2
          ref={headingRef}
          style={{
            fontFamily: "'Space Grotesk', sans-serif",
            fontSize: 'clamp(28px, 4vw, 42px)',
            fontWeight: 600,
            letterSpacing: '-0.02em',
            lineHeight: 1.15,
            color: '#1A1A1A',
          }}
        >
          {headingText}
        </h2>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-10 mt-16">
          {STEPS.map((step) => (
            <div
              key={step.num}
              className="hiw-card group p-10 transition-all duration-400"
              style={{
                background: 'rgba(255, 255, 255, 0.6)',
                border: '1px solid rgba(26, 26, 26, 0.08)',
                borderRadius: '20px',
                cursor: 'default',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.transform = 'translateY(-4px)';
                e.currentTarget.style.boxShadow = '0 12px 40px rgba(26, 26, 26, 0.08)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.transform = 'translateY(0)';
                e.currentTarget.style.boxShadow = 'none';
              }}
            >
              <span
                className="block uppercase tracking-widest"
                style={{
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: '12px',
                  color: '#C17F59',
                  fontWeight: 600,
                  letterSpacing: '0.1em',
                }}
              >
                {step.num}
              </span>
              <h3
                className="mt-3"
                style={{
                  fontFamily: "'Space Grotesk', sans-serif",
                  fontSize: '22px',
                  fontWeight: 600,
                  letterSpacing: '-0.01em',
                  lineHeight: 1.3,
                  color: '#1A1A1A',
                }}
              >
                {step.title}
              </h3>
              <p
                className="mt-3"
                style={{
                  fontFamily: "'Inter', sans-serif",
                  fontSize: '15px',
                  color: '#6B6560',
                  lineHeight: 1.6,
                }}
              >
                {step.desc}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
