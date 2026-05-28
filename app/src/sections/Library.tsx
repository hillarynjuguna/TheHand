import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';

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

type LibraryProps = {
  refreshKey: number;
};

function formatTime(value?: number): string {
  if (value === undefined || value === null || Number.isNaN(value)) {
    return '--:--';
  }
  const totalSeconds = Math.max(0, Math.floor(value));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
  }
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\\]\\]/g, '\\$&');
}

function highlightText(text: string, query: string): ReactNode[] {
  const terms = Array.from(new Set((query || '').toLowerCase().match(/\w+/g) || []));
  if (!terms.length) {
    return [text];
  }
  const regex = new RegExp(`(${terms.map(escapeRegExp).join('|')})`, 'gi');
  return text.split(regex).map((part, index) => {
    if (regex.test(part)) {
      return (
        <mark key={index} className="rounded bg-[#F5E1D6] px-1" style={{ color: '#7B2F2F' }}>
          {part}
        </mark>
      );
    }
    return <span key={index}>{part}</span>;
  });
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
  const [artifacts, setArtifacts] = useState<any[]>([]);
  const [selectedArtifact, setSelectedArtifact] = useState<any | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    const timer = window.setTimeout(() => {
      if (search.trim()) {
        fetchChunkResults();
      } else {
        fetchJobs();
      }
    }, 300);

    return () => window.clearTimeout(timer);
  }, [search, statusFilter, refreshKey]);

  useEffect(() => {
    if (!search.trim() && jobs.length && !selectedJob) {
      fetchJobDetail(jobs[0].job_id);
    }
  }, [jobs, search]);

  useEffect(() => {
    if (search.trim()) {
      setSelectedJob(null);
    }
  }, [search]);

  async function fetchJobs() {
    setLoading(true);
    setError('');
    try {
      const params = new URLSearchParams();
      if (statusFilter) params.set('status', statusFilter);
      const response = await fetch(`${API_BASE}/api/jobs?${params.toString()}`);
      if (!response.ok) {
        throw new Error(`Unable to load library (${response.status})`);
      }
      const data = await response.json();
      setJobs(data.jobs ?? []);
      setChunks([]);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Unable to load saved jobs.');
    } finally {
      setLoading(false);
    }
  }

  async function fetchChunkResults() {
    setLoading(true);
    setError('');
    try {
      const params = new URLSearchParams();
      if (search.trim()) params.set('q', search.trim());
      if (statusFilter) params.set('status', statusFilter);
      const response = await fetch(`${API_BASE}/api/chunks?${params.toString()}`);
      if (!response.ok) {
        throw new Error(`Unable to search transcripts (${response.status})`);
      }
      const data = await response.json();
      setChunks(data.chunks ?? []);
      setSelectedChunk(data.chunks?.[0] ?? null);
      setJobs([]);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Unable to search transcript chunks.');
    } finally {
      setLoading(false);
    }
  }

  async function fetchJobDetail(jobId: string) {
    setDetailLoading(true);
    setError('');
    try {
      const response = await fetch(`${API_BASE}/api/job/${jobId}`);
      if (!response.ok) {
        throw new Error(`Unable to load job details (${response.status})`);
      }
      const data = await response.json();
      setSelectedJob(data as JobDetail);
      fetchArtifacts(jobId);
      setSelectedChunk(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Unable to load job details.');
    } finally {
      setDetailLoading(false);
    }
  }

  async function fetchArtifacts(jobId: string) {
    try {
      const response = await fetch(`${API_BASE}/api/job/${jobId}/artifacts`);
      if (!response.ok) throw new Error('Unable to fetch artifacts');
      const data = await response.json();
      setArtifacts(data.artifacts ?? []);
      setSelectedArtifact(null);
    } catch (err) {
      setArtifacts([]);
    }
  }

  async function viewArtifact(a: any) {
    try {
      const res = await fetch(`${API_BASE}/api/artifact/${a.artifact_id}`);
      if (!res.ok) throw new Error('Unable to load artifact');
      const data = await res.json();
      setSelectedArtifact(data);
    } catch (err) {
      setSelectedArtifact(null);
    }
  }

  async function generateArtifact(artifactType: string) {
    if (!selectedJob) return;
    try {
      const res = await fetch(`${API_BASE}/api/job/${selectedJob.job_id}/generate/${artifactType}`, { method: 'POST' });
      if (!res.ok) throw new Error('Generation failed');
      await res.json();
      // refresh artifacts list
      setTimeout(() => fetchArtifacts(selectedJob.job_id), 500);
    } catch (err) {
      // ignore for now
    }
  }

  function handleSelectJob(job: JobPreview) {
    setSelectedChunk(null);
    fetchJobDetail(job.job_id);
  }

  function handleSelectChunk(chunk: ChunkResult) {
    setSelectedChunk(chunk);
    setSelectedJob(null);
  }

  const isSearchActive = Boolean(search.trim());

  return (
    <section id="library" className="w-full" style={{ padding: '100px 0', background: '#FFFFFF' }}>
      <div className="max-w-[1200px] mx-auto px-6">
        <div className="flex flex-col lg:flex-row justify-between gap-6 items-start">
          <div>
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
              Local Transcript Workspace
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
              Build structured knowledge from saved transcripts. Search concepts, browse semantic chunks, and revisit any passage locally.
            </p>
          </div>
          <div className="flex flex-col sm:flex-row gap-3 w-full sm:w-auto">
            <button
              type="button"
              onClick={() => {
                if (isSearchActive) {
                  fetchChunkResults();
                } else {
                  fetchJobs();
                }
              }}
              className="px-5 py-3 rounded-full text-sm font-medium"
              style={{
                background: '#1A1A1A',
                color: '#F5F0E8',
                fontFamily: "'Inter', sans-serif",
              }}
            >
              Refresh workspace
            </button>
          </div>
        </div>

        <div className="mt-8 rounded-[32px] border bg-[#F8F6F2] p-5" style={{ borderColor: 'rgba(26,26,26,0.08)' }}>
          <div className="grid grid-cols-1 lg:grid-cols-[1fr_220px] gap-4">
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search transcripts and semantic concepts..."
              className="w-full h-14 px-4 rounded-3xl outline-none"
              style={{
                border: '1px solid rgba(26,26,26,0.12)',
                background: '#FFFFFF',
                fontFamily: "'Inter', sans-serif",
                color: '#1A1A1A',
              }}
            />
            <select
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
              className="w-full h-14 px-4 rounded-3xl outline-none"
              style={{
                border: '1px solid rgba(26,26,26,0.12)',
                background: '#FFFFFF',
                fontFamily: "'Inter', sans-serif",
                color: '#1A1A1A',
              }}
            >
              <option value="">All statuses</option>
              <option value="done">Done</option>
              <option value="running">Running</option>
              <option value="queued">Queued</option>
              <option value="error">Error</option>
            </select>
          </div>
          <div className="mt-4 text-sm text-[#6B6560]">
            {isSearchActive
              ? 'Semantic search will rank transcript chunks by concept similarity and exact matches.'
              : 'Browse saved jobs and open any transcript for details.'}
          </div>
        </div>

        <div className="mt-8 grid grid-cols-1 xl:grid-cols-[380px_1fr] gap-6">
          <div className="space-y-4">
            <div className="rounded-[28px] border bg-white shadow-[0_20px_80px_rgba(26,26,26,0.05)] overflow-hidden" style={{ borderColor: 'rgba(26,26,26,0.08)' }}>
              <div className="px-5 py-4 border-b" style={{ borderColor: 'rgba(26,26,26,0.08)' }}>
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div
                      className="text-sm uppercase tracking-[0.18em]"
                      style={{ color: '#C17F59', fontFamily: "'JetBrains Mono', monospace" }}
                    >
                      {isSearchActive ? 'Chunk results' : 'Recent jobs'}
                    </div>
                    <h3
                      className="mt-2"
                      style={{ fontFamily: "'Space Grotesk', sans-serif", fontSize: '20px', color: '#1A1A1A' }}
                    >
                      {isSearchActive ? 'Matching transcript sections' : 'Saved transcript history'}
                    </h3>
                  </div>
                  <div className="text-xs text-[#6B6560]">
                    {isSearchActive ? `${chunks.length} results` : `${jobs.length} jobs`}
                  </div>
                </div>
              </div>
              {loading ? (
                <div className="p-8 text-center text-sm text-[#6B6560]">Loading workspace…</div>
              ) : isSearchActive ? (
                chunks.length === 0 ? (
                  <div className="p-8 text-center text-sm text-[#6B6560]">No semantic results found. Try broader terms.</div>
                ) : (
                  <div className="divide-y" style={{ borderColor: 'rgba(26,26,26,0.08)' }}>
                    {chunks.map((chunk) => (
                      <button
                        key={chunk.chunk_id}
                        type="button"
                        onClick={() => handleSelectChunk(chunk)}
                        className="w-full text-left px-5 py-4 hover:bg-[#f5f0e8] transition-colors"
                        style={{ background: selectedChunk?.chunk_id === chunk.chunk_id ? 'rgba(193,127,89,0.08)' : 'transparent' }}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <div className="text-sm font-semibold" style={{ color: '#1A1A1A', fontFamily: "'Inter', sans-serif" }}>
                              {chunk.source_type === 'url' ? chunk.source : chunk.filename || chunk.source}
                            </div>
                            <div className="mt-2 text-sm leading-6" style={{ color: '#6B6560', fontFamily: "'Inter', sans-serif" }}>
                              {highlightText(chunk.text.slice(0, 190).trim() || 'No preview available.', search)}
                            </div>
                          </div>
                          <span className="text-xs text-[#6B6560]" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                            {chunk.start_ts !== null && chunk.start_ts !== undefined ? formatTime(chunk.start_ts) : '--:--'}
                          </span>
                        </div>
                        <div className="mt-3 flex items-center justify-between gap-3 text-xs text-[#6B6560]">
                          <span>{chunk.job_status?.toUpperCase() ?? 'UNKNOWN'}</span>
                          {chunk.score !== null && chunk.score !== undefined && (
                            <span>score {chunk.score.toFixed(2)}</span>
                          )}
                        </div>
                      </button>
                    ))}
                  </div>
                )
              ) : jobs.length === 0 ? (
                <div className="p-8 text-center text-sm text-[#6B6560]">No transcripts have been saved yet. Run a transcription to populate the library.</div>
              ) : (
                <div className="divide-y" style={{ borderColor: 'rgba(26,26,26,0.08)' }}>
                  {jobs.map((job) => (
                    <button
                      key={job.job_id}
                      type="button"
                      onClick={() => handleSelectJob(job)}
                      className="w-full text-left px-5 py-4 hover:bg-[#f5f0e8] transition-colors"
                      style={{ background: selectedJob?.job_id === job.job_id ? 'rgba(193,127,89,0.08)' : 'transparent' }}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="text-sm font-semibold" style={{ color: '#1A1A1A', fontFamily: "'Inter', sans-serif" }}>
                            {job.source_type === 'url' ? job.source : job.filename || job.source}
                          </div>
                          <p className="mt-2 text-sm leading-6" style={{ color: '#6B6560', fontFamily: "'Inter', sans-serif" }}>
                            {job.preview || 'No transcript preview available.'}
                          </p>
                        </div>
                        <span className="text-xs text-[#6B6560]" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                          {job.chunk_count != null ? `${job.chunk_count} chunks` : '--'}
                        </span>
                      </div>
                      <div className="mt-3 flex items-center justify-between gap-3 text-xs text-[#6B6560]">
                        <span>{job.status.toUpperCase()}</span>
                        <span>{job.updated_at ? new Date(job.updated_at).toLocaleString() : '--'}</span>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
            {error && (
              <div className="rounded-[28px] border p-5 text-sm text-[#7B2F2F]" style={{ borderColor: 'rgba(184,92,79,0.3)', background: 'rgba(246,215,215,0.4)' }}>
                {error}
              </div>
            )}
          </div>

          <div className="rounded-[28px] border bg-white shadow-[0_20px_80px_rgba(26,26,26,0.05)] overflow-hidden" style={{ borderColor: 'rgba(26,26,26,0.08)' }}>
            <div className="px-6 py-5 border-b" style={{ borderColor: 'rgba(26,26,26,0.08)' }}>
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <div className="text-sm uppercase tracking-[0.18em]" style={{ color: '#C17F59', fontFamily: "'JetBrains Mono', monospace" }}>
                    {selectedChunk ? 'Transcript chunk' : 'Transcript detail'}
                  </div>
                  <h3 className="mt-2" style={{ fontFamily: "'Space Grotesk', sans-serif", fontSize: '22px', color: '#1A1A1A' }}>
                    {selectedChunk
                      ? `Chunk ${selectedChunk.chunk_index + 1}`
                      : selectedJob
                      ? selectedJob.source_type === 'url'
                        ? 'Saved URL transcript'
                        : 'Saved file transcript'
                      : 'Select a job or search result'}
                  </h3>
                </div>
                {selectedChunk?.score != null && (
                  <div className="rounded-full bg-[#F5E1D6] px-3 py-1 text-xs font-semibold" style={{ color: '#7B2F2F' }}>
                    Semantic score {selectedChunk.score.toFixed(2)}
                  </div>
                )}
              </div>
            </div>
            <div className="p-6">
              {detailLoading ? (
                <div className="text-sm text-[#6B6560]">Loading transcript detail…</div>
              ) : selectedChunk ? (
                <>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-5 text-sm text-[#6B6560]">
                    <div>
                      <div className="font-semibold text-[#1A1A1A]">Source</div>
                      <div>{selectedChunk.source_type === 'url' ? selectedChunk.source : selectedChunk.filename || selectedChunk.source}</div>
                    </div>
                    <div>
                      <div className="font-semibold text-[#1A1A1A]">Job status</div>
                      <div>{selectedChunk.job_status?.toUpperCase() ?? 'UNKNOWN'}</div>
                    </div>
                    <div>
                      <div className="font-semibold text-[#1A1A1A]">Segment</div>
                      <div>{selectedChunk.chunk_index + 1}</div>
                    </div>
                    <div>
                      <div className="font-semibold text-[#1A1A1A]">Timestamps</div>
                      <div>{selectedChunk.start_ts != null ? formatTime(selectedChunk.start_ts) : '--:--'} → {selectedChunk.end_ts != null ? formatTime(selectedChunk.end_ts) : '--:--'}</div>
                    </div>
                  </div>
                  <div className="mb-6">
                    <div className="mb-2 text-sm font-semibold" style={{ color: '#1A1A1A', fontFamily: "'Inter', sans-serif" }}>
                      Chunk text
                    </div>
                    <pre className="whitespace-pre-wrap rounded-3xl border p-4" style={{ background: '#F8F6F2', borderColor: 'rgba(26,26,26,0.08)', color: '#2A2A2A', fontFamily: "'JetBrains Mono', monospace" }}>
                      {highlightText(selectedChunk.text, search)}
                    </pre>
                  </div>
                  <div className="flex flex-wrap gap-3">
                    <button
                      type="button"
                      onClick={() => window.open(`${API_BASE}/api/job/${selectedChunk.job_id}/download/text`, '_blank')}
                      className="rounded-full px-4 py-2 text-sm"
                      style={{ background: '#1A1A1A', color: '#F5F0E8' }}
                    >
                      Download full transcript
                    </button>
                  </div>
                </>
              ) : selectedJob ? (
                <>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-5 text-sm text-[#6B6560]">
                    <div>
                      <div className="font-semibold text-[#1A1A1A]">Source</div>
                      <div>{selectedJob.source_type === 'url' ? selectedJob.source : selectedJob.filename || selectedJob.source}</div>
                    </div>
                    <div>
                      <div className="font-semibold text-[#1A1A1A]">Status</div>
                      <div>{selectedJob.status.toUpperCase()}</div>
                    </div>
                    <div>
                      <div className="font-semibold text-[#1A1A1A]">Model</div>
                      <div>{selectedJob.model || 'small'}</div>
                    </div>
                    <div>
                      <div className="font-semibold text-[#1A1A1A]">Updated</div>
                      <div>{selectedJob.updated_at ? new Date(selectedJob.updated_at).toLocaleString() : '--'}</div>
                    </div>
                  </div>
                  <div className="mb-6">
                    <div className="mb-2 text-sm font-semibold" style={{ color: '#1A1A1A', fontFamily: "'Inter', sans-serif" }}>
                      Transcript text
                    </div>
                    <pre className="whitespace-pre-wrap rounded-3xl border p-4" style={{ background: '#F8F6F2', borderColor: 'rgba(26,26,26,0.08)', color: '#2A2A2A', fontFamily: "'JetBrains Mono', monospace" }}>
                      {selectedJob.transcript.text || 'Transcript text will appear once the job is complete.'}
                    </pre>
                  </div>
                  <div className="flex flex-wrap gap-3">
                    <button
                      type="button"
                      onClick={() => window.open(`${API_BASE}/api/job/${selectedJob.job_id}/download/text`, '_blank')}
                      className="rounded-full px-4 py-2 text-sm"
                      style={{ background: '#1A1A1A', color: '#F5F0E8' }}
                    >
                      Download TXT
                    </button>
                    <button
                      type="button"
                      onClick={() => window.open(`${API_BASE}/api/job/${selectedJob.job_id}/download/srt`, '_blank')}
                      className="rounded-full px-4 py-2 text-sm"
                      style={{ background: '#C17F59', color: '#1A1A1A' }}
                    >
                      Export SRT
                    </button>
                    <button
                      type="button"
                      onClick={() => window.open(`${API_BASE}/api/job/${selectedJob.job_id}/download/json`, '_blank')}
                      className="rounded-full px-4 py-2 text-sm"
                      style={{ background: '#E8DDD0', color: '#1A1A1A' }}
                    >
                      Export JSON
                    </button>
                  </div>
                  <div className="mt-6">
                    <div className="mb-3 flex items-center justify-between">
                      <div className="text-sm font-semibold">Derived artifacts</div>
                      <div className="text-xs text-[#6B6560]">Generate: 
                        <button onClick={() => generateArtifact('summary')} className="ml-2 text-xs px-2 py-1 rounded bg-[#1A1A1A] text-white">Summary</button>
                        <button onClick={() => generateArtifact('chapter_map')} className="ml-2 text-xs px-2 py-1 rounded bg-[#E8DDD0] text-[#1A1A1A]">Chapters</button>
                        <button onClick={() => generateArtifact('entities')} className="ml-2 text-xs px-2 py-1 rounded bg-[#F5E1D6] text-[#7B2F2F]">Entities</button>
                        <button onClick={() => generateArtifact('topics')} className="ml-2 text-xs px-2 py-1 rounded bg-[#F5E1D6] text-[#7B2F2F]">Topics</button>
                        <button onClick={() => generateArtifact('quotes')} className="ml-2 text-xs px-2 py-1 rounded bg-[#F5E1D6] text-[#7B2F2F]">Quotes</button>
                      </div>
                    </div>
                    <div className="grid grid-cols-1 gap-3">
                      {artifacts.length === 0 ? (
                        <div className="text-sm text-[#6B6560]">No artifacts yet. Generate one to create persistent derived outputs.</div>
                      ) : (
                        artifacts.map((a) => (
                          <div key={a.artifact_id} className="p-3 rounded-lg border" style={{ borderColor: 'rgba(26,26,26,0.06)' }}>
                            <div className="flex items-center justify-between">
                              <div>
                                <div className="font-semibold">{a.title || a.artifact_type}</div>
                                <div className="text-xs text-[#6B6560]">{a.artifact_type} • {a.generation_status}</div>
                              </div>
                              <div className="flex gap-2">
                                <button onClick={() => viewArtifact(a)} className="text-sm px-3 py-1 rounded bg-[#1A1A1A] text-white">View</button>
                              </div>
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                    {selectedArtifact && (
                      <div className="mt-4 p-4 rounded-lg border bg-[#F8F6F2]" style={{ borderColor: 'rgba(26,26,26,0.06)' }}>
                        <div className="mb-2 font-semibold">{selectedArtifact.artifact_type} — {selectedArtifact.title}</div>
                        <pre className="whitespace-pre-wrap text-sm" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                          {selectedArtifact.persisted ? JSON.stringify(selectedArtifact.persisted, null, 2) : (selectedArtifact.content || 'No content yet.')}
                        </pre>
                      </div>
                    )}
                  </div>
                </>
              ) : (
                <div className="text-sm text-[#6B6560]">Use the search bar or choose a saved transcript to explore your workspace.</div>
              )}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
