import { useEffect, useRef } from 'react';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';

gsap.registerPlugin(ScrollTrigger);

const MODELS = [
  { model: 'tiny', size: '75MB', ram: '273MB', speed: '~10x', bestFor: 'Quick notes, low-end devices', recommended: false },
  { model: 'base', size: '142MB', ram: '388MB', speed: '~7x', bestFor: 'Fast transcription, clean audio', recommended: false },
  { model: 'small', size: '466MB', ram: '852MB', speed: '~4x', bestFor: 'Best balance (recommended)', recommended: true },
  { model: 'medium', size: '1.5GB', ram: '2.1GB', speed: '~2x', bestFor: 'Professional accuracy', recommended: false },
  { model: 'large-v3', size: '2.9GB', ram: '3.9GB', speed: '1x', bestFor: 'Maximum accuracy', recommended: false },
];

export default function ModelComparison() {
  const tableRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!tableRef.current) return;

    gsap.from(tableRef.current, {
      y: 40,
      opacity: 0,
      duration: 0.8,
      ease: 'power3.out',
      scrollTrigger: {
        trigger: tableRef.current,
        start: 'top 80%',
        toggleActions: 'play none none none',
      },
    });
  }, []);

  return (
    <section
      className="w-full"
      style={{ padding: '100px 0', background: 'rgba(255, 255, 255, 0.6)' }}
    >
      <div className="max-w-[1000px] mx-auto px-6">
        <h2
          className="text-center"
          style={{
            fontFamily: "'Space Grotesk', sans-serif",
            fontSize: 'clamp(24px, 3.5vw, 36px)',
            fontWeight: 600,
            letterSpacing: '-0.02em',
            lineHeight: 1.15,
            color: '#1A1A1A',
          }}
        >
          Pick Your Model
        </h2>

        <div
          ref={tableRef}
          className="model-table mt-12 overflow-x-auto"
        >
          <table className="w-full" style={{ borderCollapse: 'separate', borderSpacing: 0 }}>
            <thead>
              <tr style={{ background: '#1A1A1A' }}>
                {['Model', 'Size', 'RAM', 'Speed', 'Best For'].map((col) => (
                  <th
                    key={col}
                    className="text-left px-4 md:px-6 py-4"
                    style={{
                      fontFamily: "'Space Grotesk', sans-serif",
                      fontSize: '14px',
                      fontWeight: 600,
                      color: '#F5F0E8',
                      textTransform: 'uppercase',
                      letterSpacing: '0.08em',
                    }}
                  >
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {MODELS.map((m, i) => (
                <tr
                  key={m.model}
                  style={{
                    background: i % 2 === 0 ? 'rgba(255, 255, 255, 0.8)' : 'rgba(245, 240, 232, 0.8)',
                  }}
                >
                  <td
                    className="px-4 md:px-6 py-4"
                    style={{
                      fontFamily: "'JetBrains Mono', monospace",
                      fontSize: '14px',
                      color: '#1A1A1A',
                      fontWeight: m.recommended ? 700 : 400,
                    }}
                  >
                    <span className="flex items-center gap-2">
                      {m.model}
                      {m.recommended && (
                        <span
                          className="px-2 py-0.5 rounded-full text-xs"
                          style={{
                            background: 'rgba(90, 143, 110, 0.15)',
                            color: '#5A8F6E',
                            fontFamily: "'Inter', sans-serif",
                            fontSize: '10px',
                            fontWeight: 600,
                          }}
                        >
                          RECOMMENDED
                        </span>
                      )}
                    </span>
                  </td>
                  <td
                    className="px-4 md:px-6 py-4"
                    style={{
                      fontFamily: "'JetBrains Mono', monospace",
                      fontSize: '14px',
                      color: '#1A1A1A',
                    }}
                  >
                    {m.size}
                  </td>
                  <td
                    className="px-4 md:px-6 py-4"
                    style={{
                      fontFamily: "'JetBrains Mono', monospace",
                      fontSize: '14px',
                      color: '#1A1A1A',
                    }}
                  >
                    {m.ram}
                  </td>
                  <td
                    className="px-4 md:px-6 py-4"
                    style={{
                      fontFamily: "'JetBrains Mono', monospace",
                      fontSize: '14px',
                      color: '#1A1A1A',
                    }}
                  >
                    {m.speed}
                  </td>
                  <td
                    className="px-4 md:px-6 py-4"
                    style={{
                      fontFamily: "'Inter', sans-serif",
                      fontSize: '14px',
                      color: '#6B6560',
                    }}
                  >
                    {m.bestFor}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Speed note */}
        <p
          className="text-center mt-6"
          style={{
            fontFamily: "'Inter', sans-serif",
            fontSize: '14px',
            color: '#6B6560',
            lineHeight: 1.6,
          }}
        >
          Speed measured as real-time factor on Snapdragon 8 Gen 2.{' '}
          <span style={{ fontWeight: 600, color: '#1A1A1A' }}>small</span>{' '}
          is the sweet spot for most users — 4x faster than large with excellent accuracy.
        </p>
      </div>
    </section>
  );
}
