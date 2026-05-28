import { useEffect, useRef, useState } from 'react';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';

gsap.registerPlugin(ScrollTrigger);

const TERMINAL_LINES = [
  { type: 'prompt', text: '$ ' },
  { type: 'cmd', text: 'pkg install python ffmpeg' },
  { type: 'comment', text: '  # Install Python and FFmpeg' },
  { type: 'output', text: '' },
  { type: 'prompt', text: '$ ' },
  { type: 'cmd', text: 'pip install yt-dlp fastapi uvicorn' },
  { type: 'comment', text: '  # Install Python packages' },
  { type: 'output', text: '' },
  { type: 'prompt', text: '$ ' },
  { type: 'cmd', text: 'git clone https://github.com/ggml-org/whisper.cpp' },
  { type: 'comment', text: '  # Clone whisper.cpp' },
  { type: 'output', text: '' },
  { type: 'prompt', text: '$ ' },
  { type: 'cmd', text: 'cd whisper.cpp && bash models/download-ggml-model.sh small' },
  { type: 'comment', text: '  # Download small model (466MB)' },
  { type: 'output', text: '' },
  { type: 'prompt', text: '$ ' },
  { type: 'cmd', text: 'cmake -B build && cmake --build build -j$(nproc)' },
  { type: 'comment', text: '  # Compile whisper.cpp' },
  { type: 'output', text: '' },
  { type: 'prompt', text: '$ ' },
  { type: 'cmd', text: 'uvicorn main:app --host 0.0.0.0 --port 8080' },
  { type: 'comment', text: '  # Start the server!' },
  { type: 'output', text: '' },
  { type: 'output', text: 'INFO:     Started server process [12345]' },
  { type: 'output', text: 'INFO:     Waiting for application startup.' },
  { type: 'output', text: 'INFO:     Application startup complete.' },
  { type: 'success', text: 'INFO:     Uvicorn running on http://0.0.0.0:8080' },
];

const FULL_SCRIPT = `pkg install python ffmpeg
pip install yt-dlp fastapi uvicorn
pip install python-multipart
pip install websockets
git clone https://github.com/ggml-org/whisper.cpp
cd whisper.cpp && bash models/download-ggml-model.sh small
cmake -B build -DGGML_NO_OPENMP=ON
cmake --build build -j$(nproc)
cd ~ && mkdir transcribe-local && cd transcribe-local
# Create main.py (see full source on GitHub)
uvicorn main:app --host 0.0.0.0 --port 8080`;

export default function SetupGuide() {
  const terminalRef = useRef<HTMLDivElement>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!terminalRef.current) return;

    gsap.from(terminalRef.current, {
      y: 80,
      opacity: 0,
      duration: 1.0,
      ease: 'power3.out',
      scrollTrigger: {
        trigger: terminalRef.current,
        start: 'top 80%',
        toggleActions: 'play none none none',
      },
    });
  }, []);

  const handleCopy = () => {
    navigator.clipboard.writeText(FULL_SCRIPT);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const renderLine = (line: typeof TERMINAL_LINES[0], idx: number) => {
    if (line.type === 'output' && line.text === '') {
      return <div key={idx} className="h-1" />;
    }

    let color = '#E8DDD0';
    if (line.type === 'prompt') color = '#6B6560';
    if (line.type === 'cmd') color = '#C17F59';
    if (line.type === 'comment') color = '#6B6560';
    if (line.type === 'success') color = '#5A8F6E';

    return (
      <span key={idx} style={{ color, fontStyle: line.type === 'comment' ? 'italic' : 'normal' }}>
        {line.text}
      </span>
    );
  };

  return (
    <section
      id="setup"
      className="w-full"
      style={{ padding: '120px 0', background: '#1A1A1A' }}
    >
      <div className="max-w-[1200px] mx-auto px-6">
        <h2
          style={{
            fontFamily: "'Space Grotesk', sans-serif",
            fontSize: 'clamp(28px, 4vw, 42px)',
            fontWeight: 600,
            letterSpacing: '-0.02em',
            lineHeight: 1.15,
            color: '#F5F0E8',
          }}
        >
          Get Started in 60 Seconds
        </h2>
        <p
          className="mt-4"
          style={{
            fontFamily: "'Inter', sans-serif",
            fontSize: '17px',
            color: '#A09890',
            lineHeight: 1.6,
          }}
        >
          Install on Termux and start transcribing immediately. No accounts. No API keys.
        </p>

        {/* Terminal card */}
        <div
          ref={terminalRef}
          className="terminal-card mt-12 relative"
          style={{
            background: '#0D0D0D',
            borderRadius: '16px',
            overflow: 'hidden',
            border: '1px solid rgba(255, 255, 255, 0.08)',
          }}
        >
          {/* Terminal header */}
          <div
            className="flex items-center gap-2 px-4"
            style={{ height: '40px', background: '#1E1E1E' }}
          >
            <span className="w-3 h-3 rounded-full" style={{ background: '#B85C4F' }} />
            <span className="w-3 h-3 rounded-full" style={{ background: '#D4A574' }} />
            <span className="w-3 h-3 rounded-full" style={{ background: '#5A8F6E' }} />
            <span
              className="ml-3"
              style={{
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: '12px',
                color: '#6B6560',
              }}
            >
              termux@android:~
            </span>
          </div>

          {/* Copy button */}
          <button
            onClick={handleCopy}
            className="absolute top-12 right-4 w-9 h-9 flex items-center justify-center rounded-lg transition-colors duration-200"
            style={{ background: 'rgba(255, 255, 255, 0.08)' }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = 'rgba(255, 255, 255, 0.15)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = 'rgba(255, 255, 255, 0.08)';
            }}
            aria-label="Copy"
          >
            {copied ? (
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#5A8F6E" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="20 6 9 17 4 12" />
              </svg>
            ) : (
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#E8DDD0" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
              </svg>
            )}
          </button>

          {/* Terminal body */}
          <div
            className="p-6 overflow-auto"
            style={{
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: 'clamp(11px, 1.5vw, 14px)',
              color: '#E8DDD0',
              lineHeight: 1.8,
              maxHeight: '480px',
            }}
          >
            {TERMINAL_LINES.map((line, i) => (
              <div key={i} className="flex flex-wrap">
                {renderLine(line, i)}
              </div>
            ))}
          </div>
        </div>

        {/* Quick info pills */}
        <div className="flex flex-wrap gap-4 mt-8">
          {[
            { label: 'Storage', value: '~600MB' },
            { label: 'RAM (small model)', value: '~850MB' },
            { label: 'Setup time', value: '~3 min' },
            { label: 'Works offline', value: 'Yes' },
          ].map((item) => (
            <div
              key={item.label}
              className="flex items-center gap-2 px-4 py-2 rounded-full"
              style={{
                background: 'rgba(255, 255, 255, 0.06)',
                border: '1px solid rgba(255, 255, 255, 0.08)',
              }}
            >
              <span
                style={{
                  fontFamily: "'Inter', sans-serif",
                  fontSize: '13px',
                  color: '#A09890',
                }}
              >
                {item.label}
              </span>
              <span
                style={{
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: '13px',
                  color: '#F5F0E8',
                  fontWeight: 600,
                }}
              >
                {item.value}
              </span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
