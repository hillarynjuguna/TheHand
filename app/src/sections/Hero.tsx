import { useCallback, useEffect, useRef, useState } from 'react';
import gsap from 'gsap';
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Clock3,
  Database,
  FileAudio,
  Link2,
  Loader2,
  Radio,
  UploadCloud,
  Wifi,
  WifiOff,
} from 'lucide-react';
import { useOrganicFlow } from '../hooks/useOrganicFlow';

const PIPELINE_STEPS = [
  { label: 'yt-dlp', desc: 'extract audio', key: 'yt-dlp' },
  { label: 'ffmpeg', desc: 'normalize media', key: 'ffmpeg' },
  { label: 'whisper.cpp', desc: 'local transcription', key: 'whisper.cpp' },
  { label: 'workspace', desc: 'persist transcript', key: 'output' },
];

const STEP_KEY_TO_INDEX: Record<string, number> = {
  'yt-dlp': 0,
  ffmpeg: 1,
  'whisper.cpp': 2,
  output: 3,
};

const API_BASE = import.meta.env.VITE_API_BASE ?? (typeof window !== 'undefined' ? window.location.origin : 'http://localhost:8080');

type HeroProps = {
  onJobDone?: () => void;
};

type ConnectionMode = 'checking' | 'online' | 'offline' | 'demo' | 'websocket' | 'polling';

type JobStatusMessage = {
  step?: string;
  status?: string;
  error?: string;
  detail?: string;
  transcript?: { text?: string };
};

function extractUrls(text: string): string[] {
  if (!text) return [];
  const matches = text.match(/https?:\/\/[\w\-./?=&%#]+/gi) || [];
  return Array.from(new Set(matches.map((match) => match.trim())));
}

function connectionCopy(mode: ConnectionMode, serverOk: boolean | null) {
  if (mode === 'websocket') return { label: 'live runtime', tone: 'text-[#2F6B48] border-[#5A8F6E]/30 bg-[#EDF6EF]', icon: Radio };
  if (mode === 'polling') return { label: 'polling runtime', tone: 'text-[#785023] border-[#D4A574]/40 bg-[#FFF7EA]', icon: Activity };
  if (mode === 'offline') return { label: 'offline shell', tone: 'text-[#7B2F2F] border-[#B85C4F]/30 bg-[#FFF0ED]', icon: WifiOff };
  if (serverOk === true) return { label: 'server online', tone: 'text-[#2F6B48] border-[#5A8F6E]/30 bg-[#EDF6EF]', icon: Wifi };
  if (serverOk === false) return { label: 'demo mode', tone: 'text-[#785023] border-[#D4A574]/40 bg-[#FFF7EA]', icon: WifiOff };
  return { label: 'checking runtime', tone: 'text-[#5F5A54] border-black/10 bg-white', icon: Loader2 };
}

export default function Hero({ onJobDone }: HeroProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const btnRef = useRef<HTMLButtonElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const demoTimersRef = useRef<ReturnType<typeof setTimeout>[]>([]);

  const [url, setUrl] = useState('');
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [activeStep, setActiveStep] = useState(-1);
  const [showPipeline, setShowPipeline] = useState(false);
  const [transcript, setTranscript] = useState('');
  const [error, setError] = useState('');
  const [jobId, setJobId] = useState<string | null>(null);
  const [useDemo, setUseDemo] = useState(false);
  const [serverOk, setServerOk] = useState<boolean | null>(null);
  const [models, setModels] = useState<string[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>('small');
  const [urlQueue, setUrlQueue] = useState<string[]>([]);
  const [activeSource, setActiveSource] = useState('');
  const [runtimeMessage, setRuntimeMessage] = useState('Ready to ingest local media.');
  const [connectionMode, setConnectionMode] = useState<ConnectionMode>('checking');
  const [isDragging, setIsDragging] = useState(false);
  const [isOnline, setIsOnline] = useState(() => navigator.onLine);

  useOrganicFlow(canvasRef);

  useEffect(() => {
    let mounted = true;
    fetch(`${API_BASE}/api/models`)
      .then(async (response) => {
        if (!mounted || !response.ok) return;
        const json: unknown = await response.json();
        if (typeof json === 'object' && json !== null && Array.isArray((json as { models?: unknown }).models)) {
          const availableModels = (json as { models: string[] }).models;
          setModels(availableModels);
          if (availableModels.includes('small')) setSelectedModel('small');
          else if (availableModels.length) setSelectedModel(availableModels[0]);
        }
      })
      .catch(() => {});

    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    const markOnline = () => setIsOnline(true);
    const markOffline = () => {
      setIsOnline(false);
      setConnectionMode('offline');
    };
    window.addEventListener('online', markOnline);
    window.addEventListener('offline', markOffline);
    return () => {
      window.removeEventListener('online', markOnline);
      window.removeEventListener('offline', markOffline);
    };
  }, []);

  useEffect(() => {
    if (!isOnline) {
      setServerOk(false);
      setRuntimeMessage('Offline shell available. Queue work when the local server returns.');
      return;
    }

    setConnectionMode('checking');
    fetch(`${API_BASE}/api/health`, { signal: AbortSignal.timeout(3000) })
      .then((response) => (response.ok ? response.json() : Promise.reject()))
      .then((data: { whisper_ready?: boolean }) => {
        const ready = data.whisper_ready === true;
        setServerOk(true); // Server is reachable!
        setConnectionMode(ready ? 'online' : 'demo');
        setRuntimeMessage(ready ? 'Whisper runtime is reachable and ready.' : 'Backend online but Whisper not ready; demo pipeline is available.');
      })
      .catch(() => {
        setServerOk(false);
        setConnectionMode('demo');
        setRuntimeMessage('Local backend not detected; demo pipeline is available.');
      });
  }, [isOnline]);

  useEffect(() => {
    const tl = gsap.timeline({ delay: 0.15 });
    if (cardRef.current) tl.from(cardRef.current, { y: 24, opacity: 0, duration: 0.8, ease: 'power3.out' });
  }, []);

  useEffect(
    () => () => {
      if (pollRef.current) clearInterval(pollRef.current);
      demoTimersRef.current.forEach((timer) => clearTimeout(timer));
    },
    [],
  );

  const finishJob = useCallback(
    (text: string) => {
      setActiveStep(3);
      setTranscript(text || 'No transcript returned.');
      setRuntimeMessage('Transcript persisted to the local workspace.');
      setConnectionMode((mode) => (mode === 'polling' ? 'online' : mode));
      setIsTranscribing(false);
      onJobDone?.();
    },
    [onJobDone],
  );

  const failJob = useCallback((message: string) => {
    setError(message || 'Unknown runtime error.');
    setRuntimeMessage('Pipeline stopped. Review the error and retry.');
    setIsTranscribing(false);
  }, []);

  const startPolling = useCallback(
    (pollJobId: string) => {
      setConnectionMode('polling');
      setRuntimeMessage('WebSocket unavailable; polling runtime state.');
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = setInterval(async () => {
        try {
          const status = (await fetch(`${API_BASE}/api/job/${pollJobId}`).then((response) => response.json())) as JobStatusMessage;
          const stepIdx = STEP_KEY_TO_INDEX[status.step || ''] ?? -1;
          setActiveStep(stepIdx);
          if (status.step) setRuntimeMessage(`Processing via ${status.step}.`);
          if (status.status === 'done') {
            if (pollRef.current) clearInterval(pollRef.current);
            finishJob(status.transcript?.text ?? '');
          } else if (status.status === 'error') {
            if (pollRef.current) clearInterval(pollRef.current);
            failJob(status.error ?? status.detail ?? 'Unknown error');
          }
        } catch {
          setRuntimeMessage('Waiting for runtime status...');
        }
      }, 900);
    },
    [failJob, finishJob],
  );

  const watchJob = useCallback(
    (watchJobId: string) => {
      const wsUrl = `${API_BASE.replace(/^http/, 'ws')}/ws/job/${watchJobId}`;
      let ws: WebSocket | null = null;
      let opened = false;
      try {
        ws = new WebSocket(wsUrl);
        ws.onopen = () => {
          opened = true;
          setConnectionMode('websocket');
          setRuntimeMessage('Live runtime stream connected.');
        };
        ws.onmessage = (event) => {
          try {
            const status = JSON.parse(event.data as string) as JobStatusMessage;
            const stepIdx = STEP_KEY_TO_INDEX[status.step || ''] ?? -1;
            setActiveStep(stepIdx);
            if (status.step) setRuntimeMessage(`Processing via ${status.step}.`);
            if (status.status === 'done') {
              ws?.close();
              finishJob(status.transcript?.text ?? '');
            } else if (status.status === 'error') {
              ws?.close();
              failJob(status.error ?? status.detail ?? 'Unknown error');
            }
          } catch {
            setRuntimeMessage('Received malformed runtime event.');
          }
        };
        ws.onerror = () => {
          if (!opened) startPolling(watchJobId);
        };
        ws.onclose = () => {
          if (!opened && isTranscribing) startPolling(watchJobId);
        };
      } catch {
        startPolling(watchJobId);
      }
    },
    [failJob, finishJob, isTranscribing, startPolling],
  );

  const runDemo = useCallback(
    (source = 'demo source') => {
      setUseDemo(true);
      setShowPipeline(true);
      setIsTranscribing(true);
      setActiveSource(source);
      setActiveStep(0);
      setTranscript('');
      setError('');
      setConnectionMode(isOnline ? 'demo' : 'offline');
      setRuntimeMessage('Simulating a local pipeline while backend is unavailable.');

      demoTimersRef.current.forEach((timer) => clearTimeout(timer));
      const delays = [500, 1300, 2500, 3800];
      demoTimersRef.current = delays.map((delay, index) =>
        setTimeout(() => {
          setActiveStep(index);
          setRuntimeMessage(`Demo: ${PIPELINE_STEPS[index].desc}.`);
        }, delay),
      );

      demoTimersRef.current.push(
        setTimeout(() => {
          finishJob(
            `[Demo mode — server not detected]\n\n` +
              `[00:00:00] TheHand keeps transcription work local and recoverable.\n` +
              `[00:00:04] The runtime reports extraction, conversion, transcription, and persistence.\n` +
              `[00:00:09] Saved artifacts remain available in the workspace for later exploration.\n\n` +
              `Start the backend to process real media.`,
          );
        }, 4600),
      );
    },
    [finishJob, isOnline],
  );

  const runRealTranscription = useCallback(
    async (sourceUrl: string) => {
      setUseDemo(false);
      setShowPipeline(true);
      setIsTranscribing(true);
      setActiveSource(sourceUrl);
      setActiveStep(0);
      setTranscript('');
      setError('');
      setRuntimeMessage('Submitting URL to the local ingestion runtime.');

      try {
        const body = new FormData();
        body.append('url', sourceUrl);
        body.append('model', selectedModel || 'small');
        body.append('language', 'auto');

        const response = await fetch(`${API_BASE}/api/transcribe/url`, { method: 'POST', body });
        if (!response.ok) {
          let detail = '';
          try {
            const json = (await response.json()) as { detail?: unknown };
            if (Array.isArray(json.detail)) detail = json.detail.map((item) => JSON.stringify(item)).join('; ');
            else if (typeof json.detail === 'string') detail = json.detail;
            else if (json.detail) detail = JSON.stringify(json.detail);
          } catch {
            detail = await response.text().catch(() => '');
          }

          const lower = detail.toLowerCase();
          let friendly = `Server returned ${response.status}`;
          if (response.status === 422) {
            if (lower.includes('required')) friendly = 'Missing URL field. Paste a full media URL and retry.';
            else friendly = 'Invalid request. Check the URL and model selection.';
          } else if (response.status === 400) {
            friendly = detail || 'Bad request. Check the media URL.';
          } else if (response.status >= 500) {
            friendly = 'Server error. Check backend logs, then retry.';
          }
          throw new Error(`${friendly}${detail ? ` (${detail})` : ''}`);
        }

        const data = (await response.json()) as { job_id: string };
        setJobId(data.job_id);
        setRuntimeMessage('Job accepted. Waiting for live runtime events.');
        watchJob(data.job_id);
      } catch (err: unknown) {
        failJob(err instanceof Error ? err.message : 'Request failed');
      }
    },
    [failJob, selectedModel, watchJob],
  );

  const runFileTranscription = useCallback(
    async (file: File) => {
      if (!serverOk) {
        runDemo(file.name);
        return;
      }

      setUseDemo(false);
      setShowPipeline(true);
      setIsTranscribing(true);
      setActiveSource(file.name);
      setActiveStep(1);
      setTranscript('');
      setError('');
      setRuntimeMessage('Uploading local file to the transcription runtime.');

      try {
        const body = new FormData();
        body.append('file', file);
        body.append('model', selectedModel || 'small');
        body.append('language', 'auto');

        const response = await fetch(`${API_BASE}/api/transcribe/file`, { method: 'POST', body });
        if (!response.ok) throw new Error(`Server error ${response.status}`);
        const data = (await response.json()) as { job_id: string };
        setJobId(data.job_id);
        watchJob(data.job_id);
      } catch (err: unknown) {
        failJob(err instanceof Error ? err.message : 'Upload failed');
      }
    },
    [failJob, runDemo, selectedModel, serverOk, watchJob],
  );

  const addOrRunUrls = useCallback(
    (text: string) => {
      const found = extractUrls(text);
      if (found.length === 0) {
        setError('No usable URL found. Paste a full https:// link.');
        inputRef.current?.focus();
        return;
      }

      setError('');
      setUrl('');

      if (isTranscribing) {
        setUrlQueue((queue) => [...queue, ...found]);
        setRuntimeMessage(`${found.length} link${found.length > 1 ? 's' : ''} added to the queue.`);
        return;
      }

      const [first, ...rest] = found;
      setUrlQueue(rest);
      if (serverOk) runRealTranscription(first);
      else runDemo(first);
    },
    [isTranscribing, runDemo, runRealTranscription, serverOk],
  );

  useEffect(() => {
    if (!isTranscribing && urlQueue.length > 0) {
      const next = urlQueue[0];
      setUrlQueue((queue) => queue.slice(1));
      if (serverOk) runRealTranscription(next);
      else runDemo(next);
    }
  }, [isTranscribing, runDemo, runRealTranscription, serverOk, urlQueue]);

  const handleFileUpload = () => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'audio/*,video/*';
    input.onchange = () => {
      const file = input.files?.[0];
      if (file) runFileTranscription(file);
    };
    input.click();
  };

  const handleDownload = (fmt: string) => {
    if (!jobId || useDemo) {
      const blob = new Blob([transcript], { type: 'text/plain' });
      const anchor = document.createElement('a');
      anchor.href = URL.createObjectURL(blob);
      anchor.download = `transcript.${fmt === 'srt' ? 'srt' : fmt === 'json' ? 'json' : 'txt'}`;
      anchor.click();
      return;
    }
    window.open(`${API_BASE}/api/job/${jobId}/download/${fmt}`, '_blank');
  };

  const connection = connectionCopy(connectionMode, serverOk);
  const ConnectionIcon = connection.icon;
  const queuedUrls = extractUrls(url);
  const totalWorkItems = urlQueue.length + (isTranscribing ? 1 : 0);

  return (
    <section className="relative flex min-h-dvh w-full items-center overflow-hidden px-0 py-24 sm:py-28">
      <canvas ref={canvasRef} className="pointer-events-none absolute inset-0 z-0 h-full w-full opacity-70" />
      <div className="absolute inset-0 z-0 bg-[radial-gradient(circle_at_top_left,rgba(255,255,255,0.72),transparent_38%),linear-gradient(180deg,rgba(245,240,232,0.9),rgba(232,221,208,0.74))]" />

      <div className="workspace-shell relative z-10">
        <div className="grid items-center gap-6 lg:grid-cols-[minmax(0,1fr)_420px]">
          <div ref={cardRef} className="workspace-panel overflow-hidden bg-white/80 backdrop-blur-2xl">
            <div className="border-b border-black/10 p-5 sm:p-7">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <span className={`status-pill ${connection.tone}`} aria-live="polite">
                  <ConnectionIcon className={connectionMode === 'checking' ? 'h-3.5 w-3.5 animate-spin' : 'h-3.5 w-3.5'} />
                  {connection.label}
                </span>
                <span className="status-pill border-black/10 bg-[#F8F6F2] text-[#5F5A54]">
                  <Database className="h-3.5 w-3.5" />
                  local-first
                </span>
              </div>

              <div className="mt-8 max-w-3xl">
                <p className="workspace-label">Cognitive runtime</p>
                <h1 className="mt-3 font-heading text-4xl font-bold leading-[0.98] tracking-[-0.045em] text-[#171614] sm:text-6xl">
                  Ingest media into a persistent local workspace.
                </h1>
                <p className="workspace-copy mt-5 max-w-2xl">
                  Paste links or drop media. TheHand shows extraction, conversion, transcription, queue state, and saved artifacts as durable local work.
                </p>
              </div>
            </div>

            <div
              className={`p-5 transition duration-200 sm:p-7 ${isDragging ? 'bg-[#F5E1D6]/45' : 'bg-white/60'}`}
              onDragOver={(event) => {
                event.preventDefault();
                setIsDragging(true);
              }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={(event) => {
                event.preventDefault();
                setIsDragging(false);
                const file = event.dataTransfer.files?.[0];
                if (file) runFileTranscription(file);
              }}
            >
              <div className="grid gap-3 lg:grid-cols-[1fr_auto]">
                <div>
                  <label htmlFor="ingest-url" className="text-sm font-semibold text-[#27231F]">
                    Media URL or copied text
                  </label>
                  <div className="relative mt-2">
                    <Link2 className="pointer-events-none absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-[#928A82]" />
                    <input
                      id="ingest-url"
                      ref={inputRef}
                      type="url"
                      inputMode="url"
                      autoCapitalize="none"
                      autoCorrect="off"
                      placeholder="https://youtube.com/... or paste several links"
                      value={url}
                      onChange={(event) => setUrl(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter') addOrRunUrls(url);
                      }}
                      className="control-surface w-full pl-12"
                      aria-describedby="ingest-helper ingest-error"
                    />
                  </div>
                  <p id="ingest-helper" className="mt-2 text-sm leading-6 text-[#6B6560]">
                    Multiple links become a resumable queue. Files stay local to your runtime.
                  </p>
                </div>

                <div className="flex flex-col gap-3 lg:min-w-44 lg:pt-7">
                  <button
                    ref={btnRef}
                    type="button"
                    onClick={() => addOrRunUrls(url)}
                    disabled={!url.trim()}
                    className="primary-action w-full"
                  >
                    {isTranscribing ? 'Add to queue' : 'Start ingest'}
                  </button>
                  <button type="button" onClick={handleFileUpload} className="secondary-action w-full gap-2">
                    <UploadCloud className="h-4 w-4" />
                    Upload file
                  </button>
                </div>
              </div>

              {models.length > 0 && (
                <div className="mt-5 grid gap-3 rounded-2xl border border-black/10 bg-[#F8F6F2] p-3 sm:grid-cols-[1fr_auto] sm:items-center">
                  <div>
                    <div className="text-sm font-semibold text-[#27231F]">Whisper model</div>
                    <div className="text-sm text-[#6B6560]">Choose the local model before starting a job.</div>
                  </div>
                  <select
                    value={selectedModel}
                    onChange={(event) => setSelectedModel(event.target.value)}
                    className="control-surface min-w-36"
                    aria-label="Whisper model"
                  >
                    {models.map((model) => (
                      <option key={model} value={model}>
                        {model}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              {(queuedUrls.length > 1 || urlQueue.length > 0 || isTranscribing) && (
                <div className="mt-5 rounded-2xl border border-black/10 bg-white p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2 text-sm font-semibold text-[#27231F]">
                      <Clock3 className="h-4 w-4 text-[#8B563B]" />
                      Work queue
                    </div>
                    <span className="font-mono text-xs text-[#6B6560]">{totalWorkItems} active / queued</span>
                  </div>
                  <div className="mt-3 space-y-2">
                    {activeSource && (
                      <div className="flex items-start gap-3 rounded-xl bg-[#EDF6EF] px-3 py-2 text-sm text-[#2F6B48]">
                        <Loader2 className="mt-0.5 h-4 w-4 shrink-0 animate-spin" />
                        <span className="truncate">{activeSource}</span>
                      </div>
                    )}
                    {urlQueue.slice(0, 4).map((item, index) => (
                      <div key={`${item}-${index}`} className="flex items-start gap-3 rounded-xl bg-[#F8F6F2] px-3 py-2 text-sm text-[#5F5A54]">
                        <Clock3 className="mt-0.5 h-4 w-4 shrink-0" />
                        <span className="truncate">{item}</span>
                      </div>
                    ))}
                    {urlQueue.length > 4 && <div className="text-xs text-[#6B6560]">+{urlQueue.length - 4} more queued links</div>}
                  </div>
                </div>
              )}

              {error && (
                <div id="ingest-error" role="alert" className="mt-5 flex gap-3 rounded-2xl border border-[#B85C4F]/30 bg-[#FFF0ED] p-4 text-sm text-[#7B2F2F]">
                  <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" />
                  <div>
                    <div className="font-semibold">Runtime needs attention</div>
                    <div className="mt-1 leading-6">{error}</div>
                  </div>
                </div>
              )}
            </div>
          </div>

          <aside className="workspace-panel bg-[#171614] p-5 text-[#F8F6F2] shadow-[0_24px_90px_rgba(23,22,20,0.24)] sm:p-6">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="font-mono text-xs uppercase tracking-[0.18em] text-[#D4A574]">Runtime visibility</p>
                <h2 className="mt-2 font-heading text-2xl font-semibold tracking-[-0.03em]">Pipeline state</h2>
              </div>
              <Activity className="h-5 w-5 text-[#D4A574]" />
            </div>

            <div className="mt-5 rounded-2xl border border-white/10 bg-white/[0.04] p-4" aria-live="polite">
              <div className="text-sm text-[#CFC6BA]">{runtimeMessage}</div>
              {jobId && <div className="mt-2 font-mono text-[0.68rem] text-[#8D867D]">job {jobId.slice(0, 8)}</div>}
            </div>

            {showPipeline ? (
              <div className="mt-5 space-y-3">
                {PIPELINE_STEPS.map((step, index) => {
                  const complete = index < activeStep || (!isTranscribing && transcript && index <= activeStep);
                  const active = index === activeStep && isTranscribing;
                  return (
                    <div
                      key={step.key}
                      className={`rounded-2xl border p-3 transition duration-200 ${
                        active
                          ? 'border-[#D4A574]/50 bg-[#D4A574]/10'
                          : complete
                            ? 'border-[#5A8F6E]/30 bg-[#5A8F6E]/10'
                            : 'border-white/10 bg-white/[0.03]'
                      }`}
                    >
                      <div className="flex items-center gap-3">
                        <span
                          className={`runtime-dot ${
                            active
                              ? 'bg-[#D4A574] ring-[#D4A574]/15'
                              : complete
                                ? 'bg-[#5A8F6E] ring-[#5A8F6E]/15'
                                : 'bg-[#514C46] ring-white/5'
                          }`}
                        />
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center justify-between gap-3">
                            <span className="font-mono text-sm text-[#F8F6F2]">{step.label}</span>
                            {active && <span className="font-mono text-[0.68rem] uppercase tracking-[0.12em] text-[#D4A574]">running</span>}
                            {complete && <CheckCircle2 className="h-4 w-4 text-[#5A8F6E]" />}
                          </div>
                          <div className="mt-1 text-sm text-[#9F968C]">{step.desc}</div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="mt-5 rounded-2xl border border-dashed border-white/15 p-5 text-center text-sm text-[#9F968C]">
                Runtime events appear here once ingestion starts.
              </div>
            )}

            <div className={`mt-5 rounded-2xl border border-dashed p-5 text-center transition ${isDragging ? 'border-[#D4A574] bg-[#D4A574]/10' : 'border-white/15 bg-white/[0.03]'}`}>
              <FileAudio className="mx-auto h-6 w-6 text-[#D4A574]" />
              <p className="mt-3 text-sm text-[#CFC6BA]">Drop audio or video anywhere on the ingestion panel.</p>
            </div>

            {transcript && (
              <div className="mt-5 border-t border-white/10 pt-5">
                <div className="flex items-center justify-between gap-3">
                  <div className="font-mono text-xs uppercase tracking-[0.16em] text-[#D4A574]">Latest transcript</div>
                  <button type="button" onClick={() => navigator.clipboard.writeText(transcript)} className="rounded-full bg-white/10 px-3 py-1.5 text-xs text-[#F8F6F2] transition hover:bg-white/15">
                    Copy
                  </button>
                </div>
                <pre className="mt-3 max-h-48 overflow-auto whitespace-pre-wrap rounded-2xl bg-black/20 p-4 font-mono text-xs leading-6 text-[#E8DDD0]">
                  {transcript}
                </pre>
                <div className="mt-3 grid grid-cols-3 gap-2">
                  {['text', 'srt', 'json'].map((format) => (
                    <button key={format} type="button" onClick={() => handleDownload(format)} className="rounded-xl bg-white/10 px-3 py-2 text-xs font-semibold uppercase tracking-[0.08em] text-[#F8F6F2] transition hover:bg-white/15">
                      {format === 'text' ? 'TXT' : format}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </aside>
        </div>
      </div>
    </section>
  );
}
