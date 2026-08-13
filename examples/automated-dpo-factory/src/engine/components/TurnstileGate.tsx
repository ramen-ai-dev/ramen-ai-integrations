import { useEffect, useRef, useState } from "react";
import type { PublicConfig, SessionState } from "../run";
import { createSession } from "../run";

declare global {
  interface Window {
    turnstile?: {
      render(container: HTMLElement, options: { sitekey: string; action: string; theme: "light"; callback: (token: string) => void; "error-callback": () => void; "expired-callback": () => void }): string;
      remove(widgetId: string): void;
      reset(widgetId: string): void;
    };
  }
}

const SCRIPT_ID = "cloudflare-turnstile-script";

export function TurnstileGate({ config, onSession }: { config: PublicConfig; onSession: (session: SessionState) => void }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const widgetRef = useRef<string | undefined>(undefined);
  const [status, setStatus] = useState<"loading" | "ready" | "verifying" | "error">("loading");
  const [message, setMessage] = useState("Loading secure verification…");

  useEffect(() => {
    let cancelled = false;
    const render = () => {
      if (cancelled || !containerRef.current || !window.turnstile || widgetRef.current) return;
      widgetRef.current = window.turnstile.render(containerRef.current, {
        sitekey: config.turnstileSiteKey,
        action: config.turnstileAction,
        theme: "light",
        callback: async (token) => {
          setStatus("verifying");
          setMessage("Verifying and opening a one-hour session…");
          try {
            const session = await createSession(token);
            if (!cancelled) onSession(session);
          } catch (error) {
            if (!cancelled) {
              setStatus("error");
              setMessage(error instanceof Error ? `${error.message} Complete the challenge again.` : "Verification failed. Complete the challenge again.");
              if (widgetRef.current && window.turnstile) window.turnstile.reset(widgetRef.current);
            }
          }
        },
        "error-callback": () => { setStatus("error"); setMessage("Turnstile could not load. Refresh and try again."); },
        "expired-callback": () => { setStatus("ready"); setMessage("Verification expired. Complete the challenge again."); },
      });
      setStatus("ready");
      setMessage("Complete the check to unlock live governed generation.");
    };

    if (window.turnstile) render();
    else {
      const existing = document.getElementById(SCRIPT_ID) as HTMLScriptElement | null;
      const script = existing ?? document.createElement("script");
      if (!existing) {
        script.id = SCRIPT_ID;
        script.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
        script.async = true;
        script.defer = true;
        document.head.appendChild(script);
      }
      script.addEventListener("load", render, { once: true });
      script.addEventListener("error", () => { setStatus("error"); setMessage("Secure verification failed to load."); }, { once: true });
    }

    return () => {
      cancelled = true;
      if (widgetRef.current && window.turnstile) window.turnstile.remove(widgetRef.current);
      widgetRef.current = undefined;
    };
  }, [config, onSession]);

  return (
    <div className="security-gate">
      <div className="gate-icon" aria-hidden="true">◈</div>
      <div><span className="kicker">Live endpoint protection</span><h3>Verify once. Keep every key off the browser.</h3><p>The Worker verifies Turnstile, issues an unreadable secure cookie, and applies five-request-per-minute burst protection keyed to this session.</p></div>
      <div className="turnstile-area"><div ref={containerRef} /><span className={`gate-status gate-status--${status}`}>{message}</span></div>
    </div>
  );
}
