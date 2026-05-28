import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import {
  AlertTriangle,
  Archive,
  CheckCircle2,
  Clock3,
  Database,
  FileText,
  Layers3,
  Loader2,
  Radio,
  RefreshCw,
  Search,
  Sparkles,
  WifiOff,
} from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8080';

type JobPreview = {
  job_id: string;
  source_type: string;
  source: string;
  filename?: string;
  status: string;
  step?: string;
  step_status?: string;
  progress?: number;
  model?: string;
  language?: string;
  created_at?: string;
  updated_at?: string;
  preview?: string;
  error?: string;
  duration?: number;
  chunk_count?: number;
};

type ChunkResult = {
  chunk_id: number;
  job_id: string;
  chunk_index: number;
  start_ts?: number;
  end_ts?: number;
  text: string;
  score?: number | null;
  source_type: string;
  source: string;
  filename?: string;
  job_status?: string;
  model?: string;
  language?: string;
  job_updated_at?: string;
};

type JobDetail = JobPreview & {
  transcript: {
    text: string;
    srt: string;
    vtt: string;
    json_raw: string;
  };
};

type ArtifactPreview = {
  artifact_id: string;
  job_id: string;
  artifact_type: string;
  title?: string;
  generation_status: string;
  created_at?: string;
  updated_at?: string;
  generation_error?: string;
};

type ArtifactDetail = ArtifactPreview & {
  content?: string;
  persisted?: unknown;
  metadata?: unknown;
};

type RuntimeEvent = {
  type?: string;
  event_type?: string;
  status?: string;
  timestamp?: string;
  artifact_id?: string;
  job_id?: string;
  step?: string;
  detail?: unknown;
  payload?: unknown;
};

type LibraryProps = {
  refreshKey: number;
};

const ARTIFACT_ACTIONS = [
  { type: 'summary', label: 'Summary' },
  { type: 'chapter_map', label: 'Chapters' },
  { type: 'entities', label: 'Entities' },
  { type: 'topics', label: 'Topics' },
  { type: 'quotes', label: 'Quotes' },
];

function formatTime(value?: number): string {
  if (value === undefined || value === null || Number.isNaN(value)) return '--:--';
  const totalSeconds = Math.max(0, Math.floor(value));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) return `${hours}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function highlightText(text: string, query: string): ReactNode[] {
  const terms = Array.from(new Set((query || '').toLowerCase().match(/\w+/g) || []));
  if (!terms.length) return [text];
  const regex = new RegExp(`(${terms.map(escapeRegExp).join('|')})`, 'gi');
  return text.split(regex).map((part, index) => {
    if (terms.includes(part.toLowerCase())) {
      return (
        <mark key={index} className="rounded bg-[#F5E1D6] px-1 text-[#7B2F2F]">
          {part}
        </mark>
      );
    }
    return <span key={index}>{part}</span>;
  });
}

function statusMeta(status?: string) {
  const normalized = (status || 'unknown').toLowerCase();
  if (normalized === 'done' || normalized === 'complete' || normalized === 'completed' || normalized === 'fresh') {
    return { label: normalized === 'fresh' ? 'fresh' : 'done', tone: 'border-[#5A8F6E]/30 bg-[#EDF6EF] text-[#2F6B48]', icon: CheckCircle2 };
  }
  if (normalized === 'running' || normalized === 'processing') {
    return { label: 'running', tone: 'border-[#D4A574]/40 bg-[#FFF7EA] text-[#785023]', icon: Loader2 };
  }
  if (normalized === 'queued' || normalized === 'pending') {
    return { label: 'queued', tone: 'border-black/10 bg-[#F8F6F2] text-[#5F5A54]', icon: Clock3 };
  }
  if (normalized === 'error' || normalized === 'failed' || normalized === 'stale') {
    return { label: normalized, tone: 'border-[#B85C4F]/30 bg-[#FFF0ED] text-[#7B2F2F]', icon: AlertTriangle };
  }
  return { label: normalized, tone: 'border-black/10 bg-white text-[#5F5A54]', icon: Clock3 };
}

function sourceLabel(item: Pick<JobPreview, 'source_type' | 'source' | 'filename'>) {
  return item.source_type === 'url' ? item.source : item.filename || item.source || 'Untitled source';
}

function formatDate(value?: string) {
  if (!value) return '--';
  return new Date(value).toLocaleString();
}

function stringifyArtifact(artifact: ArtifactDetail) {
  if (artifact.persisted) return JSON.stringify(artifact.persisted, null, 2);
  if (artifact.content) return artifact.content;
  return 'No content persisted yet.';
}

export default function Library({ refreshKey }: LibraryProps) {
  const [jobs, setJobs] = useState<JobPreview[]>([]);
  const [chunks, setChunks] = useState<ChunkResult[]>([]);
  const [selectedJob, setSelectedJob] = useState<JobDetail | null>(null);
  const [selectedChunk, setSelectedChunk] = useState<ChunkResult | null>(null);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [artifacts, setArtifacts] = useState<ArtifactPreview[]>([]);
  const [selectedArtifact, setSelectedArtifact] = useState<ArtifactDetail | null>(null);
  const [runtimeEvents, setRuntimeEvents] = useState<RuntimeEvent[]>([]);
  const [socketState, setSocketState] = useState<'idle' | 'connected' | 'reconnecting' | 'offline'>('idle');
  const [error, setError] = useState('');
  const wsRef = useRef<WebSocket | null>(null);

  const isSearchActive = Boolean(search.trim());

  const stats = useMemo(() => {
    const running = jobs.filter((job) => ['running', 'processing'].includes(job.status)).length;
    const queued = jobs.filter((job) => ['queued', 'pending'].includes(job.status)).length;
    const failed = jobs.filter((job) => ['error', 'failed'].includes(job.status)).length;
    return { saved: jobs.length, running, queued, failed, artifacts: artifacts.length };
  }, [artifacts.length, jobs]);

  const fetchJobs = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const params = new URLSearchParams();
      if (statusFilter) params.set('status', statusFilter);
      const response = await fetch(`${API_BASE}/api/jobs?${params.toString()}`);
      if (!response.ok) throw new Error(`Unable to load library (${response.status})`);
      const data = (await response.json()) as { jobs?: JobPreview[] };
      setJobs(data.jobs ?? []);
      setChunks([]);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Unable to load saved jobs.');
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  const fetchChunkResults = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const params = new URLSearchParams();
      if (search.trim()) params.set('q', search.trim());
      if (statusFilter) params.set('status', statusFilter);
      const response = await fetch(`${API_BASE}/api/chunks?${params.toString()}`);
      if (!response.ok) throw new Error(`Unable to search transcripts (${response.status})`);
      const data = (await response.json()) as { chunks?: ChunkResult[] };
      setChunks(data.chunks ?? []);
      setSelectedChunk(data.chunks?.[0] ?? null);
      setJobs([]);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Unable to search transcript chunks.');
    } finally {
      setLoading(false);
    }
  }, [search, statusFilter]);

  const fetchArtifacts = useCallback(async (selectedJobId: string) => {
    try {
      const response = await fetch(`${API_BASE}/api/job/${selectedJobId}/artifacts`);
      if (!response.ok) throw new Error('Unable to fetch artifacts');
      const data = (await response.json()) as { artifacts?: ArtifactPreview[] };
      setArtifacts(data.artifacts ?? []);
      setSelectedArtifact(null);
    } catch {
      setArtifacts([]);
    }
  }, []);

  const fetchJobDetail = useCallback(async (selectedJobId: string) => {
    setDetailLoading(true);
    setError('');
    try {
      const response = await fetch(`${API_BASE}/api/job/${selectedJobId}`);
      if (!response.ok) throw new Error(`Unable to load job details (${response.status})`);
      const data = (await response.json()) as JobDetail;
      setSelectedJob(data);
      setSelectedChunk(null);
      void fetchArtifacts(selectedJobId);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Unable to load job details.');
    } finally {
      setDetailLoading(false);
    }
  }, [fetchArtifacts]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      if (search.trim()) {
        void fetchChunkResults();
      } else {
        void fetchJobs();
      }
    }, 300);
    return () => window.clearTimeout(timer);
  }, [fetchChunkResults, fetchJobs, refreshKey, search]);

  useEffect(() => {
    if (!search.trim() && jobs.length && !selectedJob) {
      void fetchJobDetail(jobs[0].job_id);
    }
  }, [fetchJobDetail, jobs, search, selectedJob]);

  useEffect(() => {
    if (search.trim()) {
      setSelectedJob(null);
      setArtifacts([]);
      setSelectedArtifact(null);
    }
  }, [search]);

  useEffect(() => {
    if (!selectedJob) {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      setSocketState('idle');
      return;
    }

    const wsUrl = `${API_BASE.replace(/^http/, 'ws')}/ws/job/${selectedJob.job_id}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;
    setSocketState('reconnecting');

    ws.onopen = () => setSocketState('connected');
    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data as string) as RuntimeEvent;
        setRuntimeEvents((events) => [message, ...events].slice(0, 60));
        if (message.type === 'artifact_update' || message.type === 'artifact_progress' || message.type === 'artifact_complete') {
          setArtifacts((previous) =>
            previous.map((artifact) =>
              artifact.artifact_id === message.artifact_id ? { ...artifact, generation_status: message.status || artifact.generation_status } : artifact,
            ),
          );
          if (message.type === 'artifact_complete') {
            window.setTimeout(() => void fetchArtifacts(selectedJob.job_id), 400);
          }
        }
      } catch {
        setRuntimeEvents((events) => [{ type: 'malformed_event', status: 'ignored', timestamp: new Date().toISOString() }, ...events].slice(0, 60));
      }
    };
    ws.onerror = () => setSocketState('offline');
    ws.onclose = () => setSocketState('offline');

    return () => {
      try {
        ws.close();
      } catch {
        // no-op
      }
      wsRef.current = null;
    };
  }, [fetchArtifacts, selectedJob]);

  async function viewArtifact(artifact: ArtifactPreview) {
    try {
      const response = await fetch(`${API_BASE}/api/artifact/${artifact.artifact_id}`);
      if (!response.ok) throw new Error('Unable to load artifact');
      const data = (await response.json()) as ArtifactDetail;
      setSelectedArtifact(data);
    } catch {
      setSelectedArtifact(null);
      setError('Unable to load artifact content.');
    }
  }

  async function generateArtifact(artifactType: string) {
    if (!selectedJob) return;
    setRuntimeEvents((events) => [{ type: 'artifact_requested', status: artifactType, timestamp: new Date().toISOString(), job_id: selectedJob.job_id }, ...events]);
    try {
      const response = await fetch(`${API_BASE}/api/job/${selectedJob.job_id}/generate/${artifactType}`, { method: 'POST' });
      if (!response.ok) throw new Error('Generation failed');
      await response.json();
      window.setTimeout(() => void fetchArtifacts(selectedJob.job_id), 500);
    } catch {
      setError(`Unable to generate ${artifactType}. Check the runtime and retry.`);
    }
  }

  function handleSelectJob(job: JobPreview) {
    setSelectedChunk(null);
    setSelectedArtifact(null);
    void fetchJobDetail(job.job_id);
  }

  function handleSelectChunk(chunk: ChunkResult) {
    setSelectedChunk(chunk);
    setSelectedJob(null);
    setSelectedArtifact(null);
  }

  const socketMeta = socketState === 'connected'
    ? { label: 'live events', tone: 'border-[#5A8F6E]/30 bg-[#EDF6EF] text-[#2F6B48]', icon: Radio }
    : socketState === 'offline'
      ? { label: 'event stream offline', tone: 'border-[#B85C4F]/30 bg-[#FFF0ED] text-[#7B2F2F]', icon: WifiOff }
      : socketState === 'reconnecting'
        ? { label: 'connecting', tone: 'border-[#D4A574]/40 bg-[#FFF7EA] text-[#785023]', icon: Loader2 }
        : { label: 'select transcript', tone: 'border-black/10 bg-white text-[#5F5A54]', icon: Database };
  const SocketIcon = socketMeta.icon;

  return (
    <section id="library" className="w-full bg-white py-20 sm:py-24">
      <div className="workspace-shell">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl">
            <p className="workspace-label">Persistent workspace</p>
            <h2 className="workspace-title mt-3">Library as a local cognitive runtime.</h2>
            <p className="workspace-copy mt-4">
              Search saved transcripts, inspect runtime state, and open durable artifacts without losing the operational thread.
            </p>
          </div>
          <button
            type="button"
            onClick={() => {
              if (isSearchActive) void fetchChunkResults();
              else void fetchJobs();
            }}
            className="secondary-action gap-2 self-start lg:self-auto"
          >
            <RefreshCw className="h-4 w-4" />
            Refresh workspace
          </button>
        </div>

        <div className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          {[
            { label: 'Saved jobs', value: stats.saved, icon: Archive },
            { label: 'Running', value: stats.running, icon: Loader2 },
            { label: 'Queued', value: stats.queued, icon: Clock3 },
            { label: 'Failed', value: stats.failed, icon: AlertTriangle },
            { label: 'Artifacts', value: stats.artifacts, icon: Layers3 },
          ].map((item) => (
            <div key={item.label} className="workspace-panel-muted p-4">
              <div className="flex items-center justify-between gap-3">
                <span className="text-sm text-[#6B6560]">{item.label}</span>
                <item.icon className="h-4 w-4 text-[#8B563B]" />
              </div>
              <div className="mt-3 font-mono text-2xl font-semibold text-[#171614]">{item.value}</div>
            </div>
          ))}
        </div>

        <div className="workspace-panel-muted mt-8 p-4 sm:p-5">
          <div className="grid gap-4 lg:grid-cols-[1fr_220px]">
            <div>
              <label htmlFor="workspace-search" className="text-sm font-semibold text-[#27231F]">
                Search transcripts and semantic concepts
              </label>
              <div className="relative mt-2">
                <Search className="pointer-events-none absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-[#928A82]" />
                <input
                  id="workspace-search"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Search phrases, topics, names, or remembered moments..."
                  className="control-surface w-full pl-12"
                />
              </div>
            </div>
            <div>
              <label htmlFor="status-filter" className="text-sm font-semibold text-[#27231F]">
                Runtime status
              </label>
              <select id="status-filter" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)} className="control-surface mt-2 w-full">
                <option value="">All statuses</option>
                <option value="done">Done</option>
                <option value="running">Running</option>
                <option value="queued">Queued</option>
                <option value="error">Error</option>
              </select>
            </div>
          </div>
          <p className="mt-3 text-sm leading-6 text-[#6B6560]">
            {isSearchActive ? 'Search opens transcript chunks and keeps their parent job recoverable.' : 'Browse the durable job timeline and inspect artifacts in context.'}
          </p>
        </div>

        <div className="mt-8 grid gap-6 xl:grid-cols-[390px_minmax(0,1fr)]">
          <div className="space-y-4">
            <div className="workspace-panel overflow-hidden">
              <div className="border-b border-black/10 p-5">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="workspace-label">{isSearchActive ? 'Chunk results' : 'Transcript timeline'}</p>
                    <h3 className="mt-2 font-heading text-xl font-semibold tracking-[-0.02em] text-[#171614]">
                      {isSearchActive ? 'Matching sections' : 'Saved work'}
                    </h3>
                  </div>
                  <span className="font-mono text-xs text-[#6B6560]">{isSearchActive ? `${chunks.length} results` : `${jobs.length} jobs`}</span>
                </div>
              </div>

              {loading ? (
                <div className="space-y-3 p-5" aria-live="polite">
                  {[0, 1, 2].map((item) => (
                    <div key={item} className="h-24 animate-pulse rounded-2xl bg-[#F8F6F2]" />
                  ))}
                </div>
              ) : isSearchActive ? (
                chunks.length === 0 ? (
                  <div className="p-8 text-center text-sm leading-6 text-[#6B6560]">No semantic results found. Try a broader concept or clear filters.</div>
                ) : (
                  <div className="divide-y divide-black/10">
                    {chunks.map((chunk) => {
                      const selected = selectedChunk?.chunk_id === chunk.chunk_id;
                      const meta = statusMeta(chunk.job_status);
                      const MetaIcon = meta.icon;
                      return (
                        <button
                          key={chunk.chunk_id}
                          type="button"
                          onClick={() => handleSelectChunk(chunk)}
                          className={`w-full cursor-pointer px-5 py-4 text-left transition hover:bg-[#F8F6F2] ${selected ? 'bg-[#F5E1D6]/45 ring-1 ring-inset ring-[#C17F59]/30' : ''}`}
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <div className="truncate text-sm font-semibold text-[#171614]">{sourceLabel(chunk)}</div>
                              <div className="mt-2 line-clamp-3 text-sm leading-6 text-[#5F5A54]">
                                {highlightText(chunk.text.slice(0, 230).trim() || 'No preview available.', search)}
                              </div>
                            </div>
                            <span className="shrink-0 font-mono text-xs text-[#6B6560]">{formatTime(chunk.start_ts)}</span>
                          </div>
                          <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
                            <span className={`status-pill ${meta.tone}`}>
                              <MetaIcon className={meta.label === 'running' ? 'h-3.5 w-3.5 animate-spin' : 'h-3.5 w-3.5'} />
                              {meta.label}
                            </span>
                            {chunk.score != null && <span className="font-mono text-xs text-[#6B6560]">score {chunk.score.toFixed(2)}</span>}
                          </div>
                        </button>
                      );
                    })}
                  </div>
                )
              ) : jobs.length === 0 ? (
                <div className="p-8 text-center text-sm leading-6 text-[#6B6560]">
                  No transcripts are saved yet. Start an ingest to create the first durable workspace entry.
                </div>
              ) : (
                <div className="divide-y divide-black/10">
                  {jobs.map((job) => {
                    const selected = selectedJob?.job_id === job.job_id;
                    const meta = statusMeta(job.status);
                    const MetaIcon = meta.icon;
                    return (
                      <button
                        key={job.job_id}
                        type="button"
                        onClick={() => handleSelectJob(job)}
                        className={`w-full cursor-pointer px-5 py-4 text-left transition hover:bg-[#F8F6F2] ${selected ? 'bg-[#F5E1D6]/45 ring-1 ring-inset ring-[#C17F59]/30' : ''}`}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <div className="truncate text-sm font-semibold text-[#171614]">{sourceLabel(job)}</div>
                            <p className="mt-2 line-clamp-3 text-sm leading-6 text-[#5F5A54]">{job.preview || job.error || 'No transcript preview available.'}</p>
                          </div>
                          <span className="shrink-0 font-mono text-xs text-[#6B6560]">{job.chunk_count != null ? `${job.chunk_count} chunks` : '--'}</span>
                        </div>
                        <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
                          <span className={`status-pill ${meta.tone}`}>
                            <MetaIcon className={meta.label === 'running' ? 'h-3.5 w-3.5 animate-spin' : 'h-3.5 w-3.5'} />
                            {meta.label}
                          </span>
                          <span className="font-mono text-xs text-[#6B6560]">{formatDate(job.updated_at)}</span>
                        </div>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>

            {error && (
              <div role="alert" className="flex gap-3 rounded-[1.5rem] border border-[#B85C4F]/30 bg-[#FFF0ED] p-5 text-sm text-[#7B2F2F]">
                <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" />
                <div>{error}</div>
              </div>
            )}
          </div>

          <div className="space-y-6">
            <div className="workspace-panel overflow-hidden">
              <div className="border-b border-black/10 p-5 sm:p-6">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <p className="workspace-label">{selectedChunk ? 'Transcript chunk' : 'Transcript detail'}</p>
                    <h3 className="mt-2 font-heading text-2xl font-semibold tracking-[-0.03em] text-[#171614]">
                      {selectedChunk
                        ? `Chunk ${selectedChunk.chunk_index + 1}`
                        : selectedJob
                          ? sourceLabel(selectedJob)
                          : 'Select saved work'}
                    </h3>
                  </div>
                  <span className={`status-pill ${socketMeta.tone}`}>
                    <SocketIcon className={socketState === 'reconnecting' ? 'h-3.5 w-3.5 animate-spin' : 'h-3.5 w-3.5'} />
                    {socketMeta.label}
                  </span>
                </div>
              </div>

              <div className="p-5 sm:p-6">
                {detailLoading ? (
                  <div className="space-y-3">
                    <div className="h-20 animate-pulse rounded-2xl bg-[#F8F6F2]" />
                    <div className="h-64 animate-pulse rounded-2xl bg-[#F8F6F2]" />
                  </div>
                ) : selectedChunk ? (
                  <ChunkDetail chunk={selectedChunk} search={search} />
                ) : selectedJob ? (
                  <JobDetailView
                    job={selectedJob}
                    artifacts={artifacts}
                    selectedArtifact={selectedArtifact}
                    runtimeEvents={runtimeEvents}
                    onGenerate={(type) => void generateArtifact(type)}
                    onViewArtifact={(artifact) => void viewArtifact(artifact)}
                  />
                ) : (
                  <div className="rounded-3xl border border-dashed border-black/10 bg-[#F8F6F2] p-8 text-center text-sm leading-6 text-[#6B6560]">
                    Choose a transcript or search result to inspect source, status, transcript text, and derived artifacts.
                  </div>
                )}
              </div>
            </div>

            {(selectedJob || runtimeEvents.length > 0) && (
              <RuntimeTimeline events={runtimeEvents} selectedArtifact={selectedArtifact} />
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

function ChunkDetail({ chunk, search }: { chunk: ChunkResult; search: string }) {
  const meta = statusMeta(chunk.job_status);
  const MetaIcon = meta.icon;

  return (
    <>
      <div className="grid gap-3 text-sm sm:grid-cols-2">
        {[
          ['Source', sourceLabel(chunk)],
          ['Job status', meta.label],
          ['Segment', String(chunk.chunk_index + 1)],
          ['Timestamps', `${formatTime(chunk.start_ts)} → ${formatTime(chunk.end_ts)}`],
        ].map(([label, value]) => (
          <div key={label} className="rounded-2xl border border-black/10 bg-[#F8F6F2] p-4">
            <div className="text-xs font-semibold uppercase tracking-[0.12em] text-[#8B563B]">{label}</div>
            <div className="mt-2 break-words text-[#27231F]">{value}</div>
          </div>
        ))}
      </div>
      <div className="mt-5">
        <div className={`status-pill ${meta.tone}`}>
          <MetaIcon className={meta.label === 'running' ? 'h-3.5 w-3.5 animate-spin' : 'h-3.5 w-3.5'} />
          {meta.label}
        </div>
        <pre className="mt-4 max-h-[520px] overflow-auto whitespace-pre-wrap rounded-3xl border border-black/10 bg-[#F8F6F2] p-4 font-mono text-sm leading-7 text-[#27231F]">
          {highlightText(chunk.text, search)}
        </pre>
        <button
          type="button"
          onClick={() => window.open(`${API_BASE}/api/job/${chunk.job_id}/download/text`, '_blank')}
          className="primary-action mt-4"
        >
          Download full transcript
        </button>
      </div>
    </>
  );
}

function JobDetailView({
  job,
  artifacts,
  selectedArtifact,
  runtimeEvents,
  onGenerate,
  onViewArtifact,
}: {
  job: JobDetail;
  artifacts: ArtifactPreview[];
  selectedArtifact: ArtifactDetail | null;
  runtimeEvents: RuntimeEvent[];
  onGenerate: (type: string) => void;
  onViewArtifact: (artifact: ArtifactPreview) => void;
}) {
  const meta = statusMeta(job.status);
  const MetaIcon = meta.icon;

  return (
    <>
      <div className="grid gap-3 text-sm sm:grid-cols-2 xl:grid-cols-4">
        {[
          ['Status', meta.label],
          ['Model', job.model || 'small'],
          ['Updated', formatDate(job.updated_at)],
          ['Chunks', job.chunk_count != null ? String(job.chunk_count) : '--'],
        ].map(([label, value]) => (
          <div key={label} className="rounded-2xl border border-black/10 bg-[#F8F6F2] p-4">
            <div className="text-xs font-semibold uppercase tracking-[0.12em] text-[#8B563B]">{label}</div>
            <div className="mt-2 break-words text-[#27231F]">{value}</div>
          </div>
        ))}
      </div>

      <div className="mt-5 flex flex-wrap items-center gap-3">
        <span className={`status-pill ${meta.tone}`}>
          <MetaIcon className={meta.label === 'running' ? 'h-3.5 w-3.5 animate-spin' : 'h-3.5 w-3.5'} />
          {meta.label}
        </span>
        <button type="button" onClick={() => window.open(`${API_BASE}/api/job/${job.job_id}/download/text`, '_blank')} className="secondary-action">
          Download TXT
        </button>
        <button type="button" onClick={() => window.open(`${API_BASE}/api/job/${job.job_id}/download/srt`, '_blank')} className="secondary-action">
          Export SRT
        </button>
        <button type="button" onClick={() => window.open(`${API_BASE}/api/job/${job.job_id}/download/json`, '_blank')} className="secondary-action">
          Export JSON
        </button>
      </div>

      <div className="mt-6">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div>
            <p className="workspace-label">Transcript body</p>
            <h4 className="mt-1 font-heading text-xl font-semibold tracking-[-0.02em] text-[#171614]">Persisted text</h4>
          </div>
          <FileText className="h-5 w-5 text-[#8B563B]" />
        </div>
        <pre className="max-h-[520px] overflow-auto whitespace-pre-wrap rounded-3xl border border-black/10 bg-[#F8F6F2] p-4 font-mono text-sm leading-7 text-[#27231F]">
          {job.transcript.text || job.error || 'Transcript text will appear once the job is complete.'}
        </pre>
      </div>

      <div className="mt-8 rounded-3xl border border-black/10 bg-[#F8F6F2] p-4 sm:p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <p className="workspace-label">Derived artifacts</p>
            <h4 className="mt-1 font-heading text-xl font-semibold tracking-[-0.02em] text-[#171614]">Generated workspace objects</h4>
            <p className="mt-2 text-sm leading-6 text-[#6B6560]">Artifacts persist beside the transcript and report queued/running/error lifecycle states.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            {ARTIFACT_ACTIONS.map((action) => (
              <button key={action.type} type="button" onClick={() => onGenerate(action.type)} className="secondary-action min-h-10 px-3">
                {action.label}
              </button>
            ))}
          </div>
        </div>

        <div className="mt-5 grid gap-3">
          {artifacts.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-black/10 bg-white p-5 text-sm leading-6 text-[#6B6560]">
              No artifacts yet. Generate one to create a durable derived output.
            </div>
          ) : (
            artifacts.map((artifact) => {
              const artifactMeta = statusMeta(artifact.generation_status);
              const ArtifactIcon = artifactMeta.icon;
              const latestEvents = runtimeEvents.filter((event) => event.artifact_id === artifact.artifact_id).slice(0, 2);
              return (
                <div key={artifact.artifact_id} className="rounded-2xl border border-black/10 bg-white p-4">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <Sparkles className="h-4 w-4 text-[#8B563B]" />
                        <span className="font-semibold text-[#171614]">{artifact.title || artifact.artifact_type}</span>
                        <span className={`status-pill ${artifactMeta.tone}`}>
                          <ArtifactIcon className={artifactMeta.label === 'running' ? 'h-3.5 w-3.5 animate-spin' : 'h-3.5 w-3.5'} />
                          {artifactMeta.label}
                        </span>
                      </div>
                      <div className="mt-2 font-mono text-xs text-[#6B6560]">{artifact.artifact_type} · {formatDate(artifact.updated_at || artifact.created_at)}</div>
                      {artifact.generation_error && <div className="mt-2 text-sm text-[#7B2F2F]">{artifact.generation_error}</div>}
                    </div>
                    <button type="button" onClick={() => onViewArtifact(artifact)} className="primary-action min-h-10 px-4">
                      View
                    </button>
                  </div>
                  {latestEvents.length > 0 && (
                    <div className="mt-3 rounded-xl bg-[#F8F6F2] p-3 text-xs leading-5 text-[#6B6560]">
                      {latestEvents.map((event, index) => (
                        <div key={`${event.timestamp}-${index}`}>
                          {(event.type || event.event_type || 'runtime event')} · {event.status || event.step || 'update'}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>

        {selectedArtifact && (
          <div className="mt-5 rounded-3xl border border-black/10 bg-white p-4">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <div className="font-semibold text-[#171614]">{selectedArtifact.title || selectedArtifact.artifact_type}</div>
                <div className="mt-1 font-mono text-xs text-[#6B6560]">{selectedArtifact.artifact_type} · {selectedArtifact.generation_status}</div>
              </div>
            </div>
            <pre className="mt-4 max-h-[420px] overflow-auto whitespace-pre-wrap rounded-2xl bg-[#F8F6F2] p-4 font-mono text-sm leading-7 text-[#27231F]">
              {stringifyArtifact(selectedArtifact)}
            </pre>
          </div>
        )}
      </div>
    </>
  );
}

function RuntimeTimeline({ events, selectedArtifact }: { events: RuntimeEvent[]; selectedArtifact: ArtifactDetail | null }) {
  const visibleEvents = selectedArtifact ? events.filter((event) => event.artifact_id === selectedArtifact.artifact_id).slice(0, 8) : events.slice(0, 8);

  return (
    <aside className="workspace-panel overflow-hidden">
      <div className="border-b border-black/10 p-5">
        <p className="workspace-label">Runtime events</p>
        <h3 className="mt-2 font-heading text-xl font-semibold tracking-[-0.02em] text-[#171614]">
          {selectedArtifact ? 'Artifact lifecycle' : 'Live operational trace'}
        </h3>
      </div>
      <div className="p-5">
        {visibleEvents.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-black/10 bg-[#F8F6F2] p-5 text-sm leading-6 text-[#6B6560]">
            No runtime events yet. Start artifact generation or keep this transcript open while processing.
          </div>
        ) : (
          <div className="space-y-3">
            {visibleEvents.map((event, index) => {
              const meta = statusMeta(event.status || event.step || event.type);
              const EventIcon = meta.icon;
              return (
                <div key={`${event.timestamp}-${event.type}-${index}`} className="flex gap-3 rounded-2xl border border-black/10 bg-[#F8F6F2] p-3">
                  <div className={`mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${meta.tone}`}>
                    <EventIcon className={meta.label === 'running' ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} />
                  </div>
                  <div className="min-w-0">
                    <div className="text-sm font-semibold text-[#171614]">{event.type || event.event_type || 'runtime event'}</div>
                    <div className="mt-1 font-mono text-xs text-[#6B6560]">{event.timestamp || new Date().toISOString()}</div>
                    <div className="mt-1 text-sm text-[#5F5A54]">{event.status || event.step || 'state update'}</div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </aside>
  );
}
