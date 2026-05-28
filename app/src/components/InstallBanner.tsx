import { useEffect, useState } from 'react';

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
}

export default function InstallBanner() {
  const [prompt, setPrompt] = useState<BeforeInstallPromptEvent | null>(null);
  const [isIOS, setIsIOS] = useState(false);
  const [showIOSHint, setShowIOSHint] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const [installed, setInstalled] = useState(false);

  useEffect(() => {
    // Already installed as standalone PWA — don't show
    if (window.matchMedia('(display-mode: standalone)').matches) {
      setInstalled(true);
      return;
    }

    // iOS: no beforeinstallprompt, show manual hint instead
    const ios = /iphone|ipad|ipod/i.test(navigator.userAgent) && !(window as any).MSStream;
    setIsIOS(ios);

    // Android / Chrome: capture install prompt
    const handler = (e: Event) => {
      e.preventDefault();
      setPrompt(e as BeforeInstallPromptEvent);
    };
    window.addEventListener('beforeinstallprompt', handler);

    window.addEventListener('appinstalled', () => setInstalled(true));

    // Show iOS hint after 4s if not dismissed
    if (ios) {
      const t = setTimeout(() => setShowIOSHint(true), 4000);
      return () => { clearTimeout(t); window.removeEventListener('beforeinstallprompt', handler); };
    }

    return () => window.removeEventListener('beforeinstallprompt', handler);
  }, []);

  const handleInstall = async () => {
    if (!prompt) return;
    await prompt.prompt();
    const { outcome } = await prompt.userChoice;
    if (outcome === 'accepted') setInstalled(true);
    setPrompt(null);
  };

  if (installed || dismissed) return null;
  if (!prompt && !(isIOS && showIOSHint)) return null;

  return (
    <div
      className="fixed bottom-0 left-0 right-0 z-50 p-4"
      style={{ paddingBottom: 'calc(env(safe-area-inset-bottom) + 16px)' }}
    >
      <div
        className="max-w-[480px] mx-auto flex items-center gap-4 px-5 py-4 rounded-2xl"
        style={{
          background: '#1A1A1A',
          border: '1px solid rgba(255,255,255,0.1)',
          boxShadow: '0 -4px 40px rgba(0,0,0,0.3)',
        }}
      >
        {/* Icon */}
        <div
          className="flex-shrink-0 w-10 h-10 rounded-xl flex items-center justify-center"
          style={{ background: 'rgba(193,127,89,0.15)' }}
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#C17F59" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 2v13M5 9l7 7 7-7"/><path d="M5 22h14"/>
          </svg>
        </div>

        {/* Text */}
        <div className="flex-1 min-w-0">
          <p style={{ fontFamily: "'Space Grotesk', sans-serif", fontSize: '14px', fontWeight: 600, color: '#F5F0E8' }}>
            Install TheHand
          </p>
          {isIOS ? (
            <p style={{ fontFamily: "'Inter', sans-serif", fontSize: '12px', color: '#A09890', marginTop: '2px' }}>
              Tap <strong style={{ color: '#C17F59' }}>Share</strong> → <strong style={{ color: '#C17F59' }}>Add to Home Screen</strong>
            </p>
          ) : (
            <p style={{ fontFamily: "'Inter', sans-serif", fontSize: '12px', color: '#A09890', marginTop: '2px' }}>
              Add to home screen for instant access
            </p>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2 flex-shrink-0">
          {!isIOS && (
            <button
              onClick={handleInstall}
              className="px-4 py-2 rounded-xl text-sm font-semibold transition-colors duration-200"
              style={{ background: '#C17F59', color: '#fff', fontFamily: "'Inter', sans-serif" }}
              onMouseEnter={e => (e.currentTarget.style.background = '#a8623e')}
              onMouseLeave={e => (e.currentTarget.style.background = '#C17F59')}
            >
              Install
            </button>
          )}
          <button
            onClick={() => setDismissed(true)}
            className="w-8 h-8 flex items-center justify-center rounded-lg transition-colors duration-200"
            style={{ background: 'rgba(255,255,255,0.06)' }}
            onMouseEnter={e => (e.currentTarget.style.background = 'rgba(255,255,255,0.12)')}
            onMouseLeave={e => (e.currentTarget.style.background = 'rgba(255,255,255,0.06)')}
            aria-label="Dismiss"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#A09890" strokeWidth="2" strokeLinecap="round">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}
