import { useEffect, useRef } from 'react';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';

gsap.registerPlugin(ScrollTrigger);

const NODES = [
  { label: 'URL / File', bg: '#C17F59', color: '#FFFFFF' },
  { label: 'yt-dlp', bg: 'rgba(193, 127, 89, 0.15)', color: '#1A1A1A' },
  { label: 'ffmpeg', bg: 'rgba(193, 127, 89, 0.15)', color: '#1A1A1A' },
  { label: 'whisper.cpp', bg: 'rgba(193, 127, 89, 0.15)', color: '#1A1A1A' },
  { label: 'Transcript', bg: '#5A8F6E', color: '#FFFFFF' },
];

export default function Architecture() {
  const sectionRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!sectionRef.current) return;

    const nodes = sectionRef.current.querySelectorAll('.pipeline-node');
    nodes.forEach((node, i) => {
      gsap.from(node, {
        x: -30,
        opacity: 0,
        duration: 0.6,
        ease: 'power3.out',
        scrollTrigger: {
          trigger: '.pipeline-container',
          start: 'top 80%',
          toggleActions: 'play none none none',
        },
        delay: i * 0.12,
      });
    });
  }, []);

  return (
    <section
      ref={sectionRef}
      className="w-full"
      style={{ padding: '120px 0', background: '#F5F0E8' }}
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
          The Architecture
        </h2>
        <p
          className="mt-4"
          style={{
            fontFamily: "'Inter', sans-serif",
            fontSize: '17px',
            color: '#6B6560',
            lineHeight: 1.6,
          }}
        >
          Simple on the surface. Robust underneath.
        </p>

        {/* Pipeline diagram */}
        <div
          className="pipeline-container mt-14 flex flex-wrap items-center justify-center gap-2 md:gap-4"
        >
          {NODES.map((node, i) => (
            <div key={node.label} className="flex items-center gap-2 md:gap-4">
              <div
                className="pipeline-node px-5 md:px-7 py-4 md:py-5 text-center whitespace-nowrap transition-transform duration-300 hover:scale-105"
                style={{
                  background: node.bg,
                  color: node.color,
                  borderRadius: '12px',
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: 'clamp(11px, 1.5vw, 13px)',
                  fontWeight: 600,
                }}
              >
                {node.label}
              </div>
              {i < NODES.length - 1 && (
                <span
                  className="text-xl md:text-2xl"
                  style={{ color: '#6B6560' }}
                >
                  →
                </span>
              )}
            </div>
          ))}
        </div>

        {/* Detailed cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mt-16">
          {[
            {
              title: 'yt-dlp',
              desc: 'Downloads audio from 1000+ sites including YouTube, TikTok, Instagram, podcasts, and more. Extracts the best quality audio stream.',
              badge: 'Downloader',
            },
            {
              title: 'ffmpeg',
              desc: 'Converts any audio format to 16kHz mono WAV — the exact format Whisper expects. Handles MP3, M4A, OPUS, OGG, FLAC, and more.',
              badge: 'Converter',
            },
            {
              title: 'whisper.cpp',
              desc: 'Georgi Gerganov\'s high-performance C++ implementation of OpenAI\'s Whisper. Optimized for ARM. Runs at 2-10x real-time speed on mobile.',
              badge: 'Transcriber',
            },
            {
              title: 'FastAPI',
              desc: 'Python async web framework serving the local UI. Handles file uploads, URL processing, model management, and API endpoints.',
              badge: 'Server',
            },
          ].map((item) => (
            <div
              key={item.title}
              className="p-6 transition-all duration-300 hover:-translate-y-1"
              style={{
                background: 'rgba(255, 255, 255, 0.6)',
                border: '1px solid rgba(26, 26, 26, 0.08)',
                borderRadius: '16px',
              }}
            >
              <div className="flex items-center gap-2 mb-3">
                <span
                  className="px-2 py-0.5 text-xs rounded-md"
                  style={{
                    background: 'rgba(193, 127, 89, 0.15)',
                    color: '#C17F59',
                    fontFamily: "'JetBrains Mono', monospace",
                    fontSize: '11px',
                    fontWeight: 600,
                  }}
                >
                  {item.badge}
                </span>
              </div>
              <h3
                style={{
                  fontFamily: "'Space Grotesk', sans-serif",
                  fontSize: '18px',
                  fontWeight: 600,
                  color: '#1A1A1A',
                }}
              >
                {item.title}
              </h3>
              <p
                className="mt-2"
                style={{
                  fontFamily: "'Inter', sans-serif",
                  fontSize: '14px',
                  color: '#6B6560',
                  lineHeight: 1.6,
                }}
              >
                {item.desc}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
