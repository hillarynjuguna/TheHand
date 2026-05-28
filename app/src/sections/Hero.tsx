import { useEffect, useRef, useState, useCallback } from 'react';
import gsap from 'gsap';
import { useOrganicFlow } from '../hooks/useOrganicFlow';

const PIPELINE_STEPS = [
  { label: 'yt-dlp',      desc: 'extract audio',    color: '#5A8F6E', key: 'yt-dlp'      },
  { label: 'ffmpeg',      desc: 'convert to WAV',   color: '#D4A574', key: 'ffmpeg'      },
  { label: 'whisper.cpp', desc: 'transcribe',        color: '#C17F59', key: 'whisper.cpp' },
  { label: 'output',      desc: 'save transcript',   color: '#5A8F6E', key: 'output'      },
];

const STEP_KEY_TO_INDEX: Record<string, number> = {
  'yt-dlp': 0, 'ffmpeg': 1, 'whisper.cpp': 2, 'output': 3,
};

// Point this at wherever your server is running.
// In Termux on the same phone: http://localhost:8080
// From another device on the same Wi-Fi: http://<phone-ip>:8080
const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8080';

type HeroProps = {
  onJobDone?: () => void;
};

export default function Hero({ onJobDone }: HeroProps) {
  const canvasRef   = useRef<HTMLCanvasElement>(null);
  const cardRef     = useRef<HTMLDivElement>(null);
  const inputRef    = useRef<HTMLInputElement>(null);
  const btnRef      = useRef<HTMLButtonElement>(null);
  const pipelineRef = useRef<HTMLDivElement>(null);
  const pollRef     = useRef<ReturnType<typeof setInterval> | null>(null);

  const [url, setUrl]                   = useState('');
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [activeStep, setActiveStep]     = useState(-1);
  const [showPipeline, setShowPipeline] = useState(false);
  const [transcript, setTranscript]     = useState('');
  const [error, setError]               = useState('');
  const [jobId, setJobId]               = useState<string | null>(null);
  const [useDemo, setUseDemo]           = useState(false);
  const [serverOk, setServerOk]         = useState<boolean | null>(null);
  const [models, setModels] = useState<string[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>('small');
  const [urlQueue, setUrlQueue] = useState<string[]>([]);

  useOrganicFlow(canvasRef);

  // fetch models once
  useEffect(() => {
    let mounted = true;
    fetch(`${API_BASE}/api/models`).then(async (r) => {
      if (!mounted) return;
      if (!r.ok) return;
      try {
        const json = await r.json();
        if (Array.isArray(json.models)) {
          setModels(json.models);
          if (json.models.includes('small')) setSelectedModel('small');
          else if (json.models.length) setSelectedModel(json.models[0]);
        }
      } catch {}
    }).catch(() => {});
    return () => { mounted = false; };
  }, []);

  // When a job finishes, automatically process the next queued URL
  // (moved below runRealTranscription to avoid referencing before declaration)

  // Check if the server is reachable on mount
  useEffect(() => {
    fetch(`${API_BASE}/api/health`, { signal: AbortSignal.timeout(3000) })
      .then(r => r.ok ? r.json() : Promise.reject())
      .then(data => setServerOk(data.whisper_ready === true))
      .catch(() => setServerOk(false));
  }, []);

  useEffect(() => {
    const tl = gsap.timeline({ delay: 0.3 });
    if (cardRef.current) tl.from(cardRef.current, { y: 40, opacity: 0, duration: 1.2, ease: 'power3.out' });
    if (inputRef.current) tl.from(inputRef.current, { y: 20, opacity: 0, duration: 0.6, ease: 'power3.out' }, '-=0.6');
    if (btnRef.current) tl.from(btnRef.current, { y: 20, opacity: 0, duration: 0.6, ease: 'power3.out' }, '-=0.4');
  }, []);

  // Clean up polling on unmount
  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  // ── Demo (simulated) pipeline ────────────────────────────────────────────
  const runDemo = useCallback(() => {
    setUseDemo(true);
    setShowPipeline(true);
    setIsTranscribing(true);
    setActiveStep(0);
    setTranscript('');
    setError('');

    const delays = [800, 1600, 3000, 4200];
    delays.forEach((delay, i) => setTimeout(() => setActiveStep(i), delay));

    setTimeout(() => {
      setIsTranscribing(false);
      setTranscript(
        `[Demo mode — server not detected]\n\n` +
        `[00:00:00] Hey everyone, welcome back to the channel.\n` +
        `[00:00:03] Today we're going to talk about running AI locally on your phone.\n` +
        `[00:00:07] It's actually way easier than you think.\n` +
        `[00:00:10] With tools like Termux, Whisper.cpp, and a simple FastAPI server...\n` +
        `[00:00:15] You can transcribe any audio without sending data to the cloud.\n` +
        `[00:00:20] Let me show you exactly how to set it up.\n\n` +
        `--- Demo transcript (start the backend to transcribe real audio) ---`
      );
    }, 5000);
  }, []);

  // ── Real pipeline ────────────────────────────────────────────────────────
  const runRealTranscription = useCallback(async (sourceUrl: string) => {
    setUseDemo(false);
    setShowPipeline(true);
    setIsTranscribing(true);
    setActiveStep(0);
    setTranscript('');
    setError('');

    try {
      const body = new FormData();
      body.append('url', sourceUrl);
      body.append('model', selectedModel || 'small');
      body.append('language', 'auto');

      const res = await fetch(`${API_BASE}/api/transcribe/url`, { method: 'POST', body });
      if (!res.ok) {
        // try to parse friendly server error
        let detail = '';
        try {
          const json = await res.json();
          if (json?.detail) {
            if (Array.isArray(json.detail)) {
              detail = json.detail.map((d: any) => d?.msg ?? JSON.stringify(d)).join('; ');
            } else if (typeof json.detail === 'string') {
              detail = json.detail;
            } else if (json.detail.msg) {
              detail = json.detail.msg;
            } else {
              detail = JSON.stringify(json.detail);
            }
          } else {
            detail = JSON.stringify(json);
          }
        } catch (e) {
          try { detail = await res.text(); } catch { detail = ''; }
        }
        const lower = (detail || '').toLowerCase();
        let friendly = `Server returned ${res.status}`;
        if (res.status === 422) {
          if (lower.includes('field required') || lower.includes('required')) friendly = 'Missing form field — please ensure a URL is provided.';
          else if (lower.includes('value is not a valid')) friendly = 'Invalid value submitted. Please check the URL format.';
          else friendly = 'Invalid request — please check the input and try again.';
        } else if (res.status === 400) {
          friendly = detail || 'Bad request';
        } else if (res.status >= 500) {
          friendly = 'Server error — check backend logs for details.';
        }
        throw new Error(`${friendly}${detail ? ` (${detail})` : ''}`);
      }

      const { job_id } = await res.json();
      setJobId(job_id);

      // Try websocket for live updates; fallback to polling
      const wsUrl = `${API_BASE.replace(/^http/, 'ws')}/ws/job/${job_id}`;
      let ws: WebSocket | null = null;
      let usedWebsocket = false;
      try {
        ws = new WebSocket(wsUrl);
        ws.onopen = () => { usedWebsocket = true; };
        ws.onmessage = (ev) => {
          try {
            const status = JSON.parse(ev.data);
            const stepIdx = STEP_KEY_TO_INDEX[status.step] ?? -1;
            setActiveStep(stepIdx);
            if (status.status === 'done') {
              ws?.close();
              setActiveStep(3);
              setTranscript(status.transcript?.text ?? 'No transcript returned.');
              setIsTranscribing(false);
              onJobDone?.();
            } else if (status.status === 'error') {
              ws?.close();
              setError(status.error ?? status?.detail ?? 'Unknown error');
              setIsTranscribing(false);
            }
          } catch (e) { /* ignore malformed messages */ }
        };
        ws.onerror = () => { /* fall back */ };
        ws.onclose = () => {
          if (!usedWebsocket) startPolling(job_id);
        };
      } catch (e) {
        startPolling(job_id);
      }

      function startPolling(job_id_inner: string) {
        pollRef.current = setInterval(async () => {
          try {
            const status = await fetch(`${API_BASE}/api/job/${job_id_inner}`).then(r => r.json());
            const stepIdx = STEP_KEY_TO_INDEX[status.step] ?? -1;
            setActiveStep(stepIdx);
            if (status.status === 'done') {
              clearInterval(pollRef.current!);
              setActiveStep(3);
              setTranscript(status.transcript?.text ?? 'No transcript returned.');
              setIsTranscribing(false);
              onJobDone?.();
            } else if (status.status === 'error') {
              clearInterval(pollRef.current!);
              setError(status.error ?? 'Unknown error');
              setIsTranscribing(false);
            }
          } catch { /* ignore */ }
        }, 800);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Request failed');
      setIsTranscribing(false);
    }
  }, [selectedModel, onJobDone]);

  function extractUrls(text: string): string[] {
    if (!text) return [];
    const regex = /https?:\/\/[\w\-./?=&%#]+/gi;
    const matches = text.match(regex) || [];
    return matches.map((s) => s.trim());
  }

  const handleTranscribe = () => {
    if (isTranscribing) return;
    if (!url.trim()) {
      setError('Please paste a valid URL before transcribing.');
      inputRef.current?.focus();
      return;
    }
    // Extract URLs from the input; allow pasting text containing one or more links.
    const found = extractUrls(url);
    if (found.length === 0) {
      setError('No valid URLs found in input. Paste a full link (https://...).');
      inputRef.current?.focus();
      return;
    }

    // If already transcribing, append to the queue; otherwise start immediately and queue rest.
    if (isTranscribing) {
      setUrlQueue((q) => [...q, ...found]);
      setError('Added to queue');
      setUrl('');
      return;
    }

    setUrl('');
    if (found.length === 1) {
      if (serverOk) runRealTranscription(found[0]);
      else runDemo();
      return;
    }

    // multiple links: start first, enqueue the rest
    const [first, ...rest] = found;
    setUrlQueue(rest);
    if (serverOk) runRealTranscription(first);
    else runDemo();
  };

  // When a job finishes, automatically process the next queued URL
  useEffect(() => {
    if (!isTranscribing && urlQueue.length > 0) {
      const next = urlQueue[0];
      setUrlQueue((q) => q.slice(1));
      if (serverOk) runRealTranscription(next);
      else runDemo();
    }
  }, [isTranscribing, urlQueue, serverOk, runRealTranscription]);

  const handleFileUpload = () => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'audio/*,video/*';
    input.onchange = async () => {
      const file = input.files?.[0];
      if (!file) return;
      setUrl(file.name);

      if (!serverOk) { runDemo(); return; }

      setUseDemo(false);
      setShowPipeline(true);
      setIsTranscribing(true);
      setActiveStep(1); // files skip yt-dlp
      setTranscript('');
      setError('');

      try {
        const body = new FormData();
        body.append('file', file);
        body.append('model', 'small');
        body.append('language', 'auto');

        const res = await fetch(`${API_BASE}/api/transcribe/file`, { method: 'POST', body });
        if (!res.ok) throw new Error(`Server error ${res.status}`);
        const { job_id } = await res.json();
        setJobId(job_id);

        pollRef.current = setInterval(async () => {
          try {
            const status = await fetch(`${API_BASE}/api/job/${job_id}`).then(r => r.json());
            const stepIdx = STEP_KEY_TO_INDEX[status.step] ?? -1;
            setActiveStep(Math.max(stepIdx, 1));
            if (status.status === 'done') {
              clearInterval(pollRef.current!);
              setActiveStep(3);
              setTranscript(status.transcript?.text ?? '');
              setIsTranscribing(false);
              onJobDone?.();
            } else if (status.status === 'error') {
              clearInterval(pollRef.current!);
              setError(status.error ?? 'Unknown error');
              setIsTranscribing(false);
            }
          } catch { /* keep polling */ }
        }, 800);
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : 'Upload failed');
        setIsTranscribing(false);
      }
    };
    input.click();
  };

  const handleDownload = (fmt: string) => {
    if (!jobId || useDemo) {
      const blob = new Blob([transcript], { type: 'text/plain' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `transcript.${fmt === 'srt' ? 'srt' : fmt === 'json' ? 'json' : 'txt'}`;
      a.click();
      return;
    }
    window.open(`${API_BASE}/api/job/${jobId}/download/${fmt}`, '_blank');
  };

  return (
    <section className="relative w-full overflow-hidden" style={{ minHeight: '100vh' }}>
      <canvas ref={canvasRef} style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', zIndex: 0, pointerEvents: 'none' }} />

      <div className="relative flex items-center justify-center px-6" style={{ zIndex: 2, height: '100%', paddingTop: '64px' }}>
        <div
          ref={cardRef}
          className="w-full max-w-[640px]"
          style={{
            background: 'rgba(255,255,255,0.25)',
            backdropFilter: 'blur(40px) saturate(1.2)',
            WebkitBackdropFilter: 'blur(40px) saturate(1.2)',
            border: '1px solid rgba(255,255,255,0.3)',
            borderRadius: '24px',
            padding: '48px',
            boxShadow: '0 8px 32px rgba(26,26,26,0.06)',
          }}
        >
          {/* Server status badge */}
          {serverOk !== null && (
            <div className="flex justify-end mb-3">
              <span className="text-xs px-2 py-1 rounded-full" style={{
                background: serverOk ? 'rgba(90,143,110,0.12)' : 'rgba(193,127,89,0.12)',
                color: serverOk ? '#5A8F6E' : '#C17F59',
                fontFamily: "'JetBrains Mono', monospace",
              }}>
                {serverOk ? '● server online' : '● demo mode'}
              </span>
            </div>
          )}

          <h1 className="text-center" style={{
            fontFamily: "'Space Grotesk', sans-serif",
            fontSize: 'clamp(28px, 5vw, 56px)',
            fontWeight: 700, letterSpacing: '-0.03em', lineHeight: 1.0, color: '#1A1A1A',
          }}>
            Your Audio, Transcribed Locally
          </h1>
          <p className="text-center mt-4" style={{
            fontFamily: "'Inter', sans-serif", fontSize: '18px', fontWeight: 400, color: '#6B6560',
          }}>
            Paste a link. Get clean text. Zero cloud. Zero friction.
          </p>

          <div className="flex flex-col gap-3 mt-10">
            <input
              ref={inputRef}
              type="text"
              aria-label="Audio or video URL"
              placeholder="Paste YouTube, TikTok, or audio URL..."
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleTranscribe()}
              className="w-full h-14 px-5 text-base outline-none transition-all duration-300 placeholder:text-[#9A9A9A]"
              style={{
                background: '#FFFFFF',
                border: '1px solid rgba(26,26,26,0.16)',
                borderRadius: '12px',
                fontFamily: "'Inter', sans-serif", fontSize: '16px', color: '#1A1A1A',
              }}
              onFocus={(e) => { e.currentTarget.style.borderColor = '#C17F59'; e.currentTarget.style.boxShadow = '0 0 0 3px rgba(193,127,89,0.15)'; }}
              onBlur={(e) => { e.currentTarget.style.borderColor = 'rgba(26,26,26,0.1)'; e.currentTarget.style.boxShadow = 'none'; }}
            />
            {/* model selector */}
            {models.length > 0 && (
              <div className="w-full flex items-center gap-3">
                <label className="text-sm" style={{ color: '#6B6560', fontFamily: "'Inter', sans-serif" }}>Model</label>
                <select value={selectedModel} onChange={(e) => setSelectedModel(e.target.value)}
                  className="h-10 px-3 rounded-md"
                  style={{ border: '1px solid rgba(26,26,26,0.08)', background: '#FFF' }}>
                  {models.map((m) => <option key={m} value={m}>{m}</option>)}
                </select>
              </div>
            )}
            {urlQueue.length > 0 && (
              <div className="text-sm text-[#6B6560] mt-2">Queued links: {urlQueue.length}. They will be processed automatically.</div>
            )}
            <button
              ref={btnRef}
              onClick={handleTranscribe}
              disabled={isTranscribing}
              className="w-full h-[52px] text-base font-semibold rounded-xl transition-colors duration-300"
              style={{
                background: isTranscribing ? '#6B6560' : '#1A1A1A',
                color: '#F5F0E8', fontFamily: "'Inter', sans-serif",
                cursor: isTranscribing ? 'wait' : 'pointer',
              }}
              onMouseEnter={(e) => { if (!isTranscribing) e.currentTarget.style.background = '#C17F59'; }}
              onMouseLeave={(e) => { if (!isTranscribing) e.currentTarget.style.background = '#1A1A1A'; }}
            >
              {isTranscribing ? 'Transcribing...' : 'Transcribe'}
            </button>

            <div className="flex items-center justify-between mt-2">
              <button onClick={handleFileUpload} className="text-sm transition-colors duration-300 hover:underline"
                style={{ color: '#C17F59', fontFamily: "'Inter', sans-serif" }}>
                Or upload audio file
              </button>
              <span className="text-sm" style={{ color: '#6B6560', fontFamily: "'Inter', sans-serif" }}>
                Advanced ▾
              </span>
            </div>
          </div>

          {/* Pipeline */}
          {showPipeline && (
            <div ref={pipelineRef} className="mt-6"
              style={{ background: '#1E1E1E', borderRadius: '12px', padding: '24px' }}>
              <div className="flex flex-col gap-3">
                {PIPELINE_STEPS.map((step, i) => (
                  <div key={step.label} className="flex items-center gap-3">
                    <span className="text-xs transition-all duration-400" style={{
                      fontFamily: "'JetBrains Mono', monospace",
                      color: i <= activeStep ? step.color : '#4a4a4a',
                      textShadow: i === activeStep ? `0 0 12px ${step.color}66` : 'none',
                    }}>●</span>
                    <span className="text-sm" style={{ fontFamily: "'JetBrains Mono', monospace", color: i <= activeStep ? '#E8DDD0' : '#4a4a4a' }}>
                      {step.label}
                    </span>
                    <span className="text-xs" style={{ fontFamily: "'JetBrains Mono', monospace", color: i <= activeStep ? '#6B6560' : '#3a3a3a' }}>
                      — {step.desc}
                    </span>
                    {i === activeStep && isTranscribing && (
                      <span className="ml-auto text-xs" style={{ fontFamily: "'JetBrains Mono', monospace", color: step.color }}>running...</span>
                    )}
                    {i < activeStep && (
                      <span className="ml-auto text-xs" style={{ fontFamily: "'JetBrains Mono', monospace", color: '#5A8F6E' }}>✓</span>
                    )}
                  </div>
                ))}
              </div>

              {/* Error */}
              {error && (
                <div className="mt-4 p-3 rounded-lg" style={{ background: 'rgba(184,92,79,0.15)', border: '1px solid rgba(184,92,79,0.3)' }}>
                  <p className="text-xs" style={{ fontFamily: "'JetBrains Mono', monospace", color: '#B85C4F' }}>{error}</p>
                </div>
              )}

              {/* Transcript output */}
              {transcript && (
                <div className="mt-4 pt-4" style={{ borderTop: '1px solid rgba(255,255,255,0.08)' }}>
                  <pre className="whitespace-pre-wrap text-xs leading-relaxed overflow-auto max-h-[200px]"
                    style={{ fontFamily: "'JetBrains Mono', monospace", color: '#E8DDD0' }}>
                    {transcript}
                  </pre>
                  <div className="flex gap-2 mt-3 flex-wrap">
                    <button onClick={() => navigator.clipboard.writeText(transcript)}
                      className="text-xs px-3 py-1.5 rounded-md"
                      style={{ background: 'rgba(255,255,255,0.08)', color: '#E8DDD0', fontFamily: "'JetBrains Mono', monospace" }}>
                      Copy
                    </button>
                    <button onClick={() => handleDownload('srt')}
                      className="text-xs px-3 py-1.5 rounded-md"
                      style={{ background: 'rgba(255,255,255,0.08)', color: '#E8DDD0', fontFamily: "'JetBrains Mono', monospace" }}>
                      Export SRT
                    </button>
                    <button onClick={() => handleDownload('json')}
                      className="text-xs px-3 py-1.5 rounded-md"
                      style={{ background: 'rgba(255,255,255,0.08)', color: '#E8DDD0', fontFamily: "'JetBrains Mono', monospace" }}>
                      Export JSON
                    </button>
                    <button onClick={() => handleDownload('text')}
                      className="text-xs px-3 py-1.5 rounded-md"
                      style={{ background: 'rgba(255,255,255,0.08)', color: '#E8DDD0', fontFamily: "'JetBrains Mono', monospace" }}>
                      Download TXT
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
