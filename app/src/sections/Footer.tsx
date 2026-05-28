const FOOTER_LINKS = [
  { label: 'GitHub', href: 'https://github.com/ggml-org/whisper.cpp' },
  { label: 'Report Issue', href: 'https://github.com/ggml-org/whisper.cpp/issues' },
  { label: 'Contribute', href: 'https://github.com/ggml-org/whisper.cpp/blob/master/CONTRIBUTING.md' },
];

export default function Footer() {
  return (
    <footer
      className="w-full"
      style={{ padding: '60px 0 40px', background: '#1A1A1A' }}
    >
      <div className="max-w-[1200px] mx-auto px-6">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-6">
          <div>
            <span
              style={{
                fontFamily: "'Space Grotesk', sans-serif",
                fontSize: '16px',
                fontWeight: 700,
                color: '#F5F0E8',
              }}
            >
              transcribe.local
            </span>
            <p
              className="mt-2"
              style={{
                fontFamily: "'Inter', sans-serif",
                fontSize: '14px',
                color: '#6B6560',
              }}
            >
              Open source. Local-first. Forever free.
            </p>
          </div>

          <div className="flex gap-6">
            {FOOTER_LINKS.map((link) => (
              <a
                key={link.label}
                href={link.href}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm transition-colors duration-300 hover:text-[#C17F59]"
                style={{
                  fontFamily: "'Inter', sans-serif",
                  color: '#6B6560',
                }}
              >
                {link.label}
              </a>
            ))}
          </div>
        </div>

        <div
          className="mt-10 pt-6"
          style={{ borderTop: '1px solid rgba(255, 255, 255, 0.08)' }}
        >
          <p
            style={{
              fontFamily: "'Inter', sans-serif",
              fontSize: '13px',
              color: '#6B6560',
            }}
          >
            Powered by Whisper.cpp, yt-dlp, and FastAPI. Built for humans who value privacy.
          </p>
        </div>
      </div>
    </footer>
  );
}
