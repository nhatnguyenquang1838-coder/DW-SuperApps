"use client";
import { useEffect, useRef, useState } from 'react';
import styles from './ArtifactViewer.module.css';

type ResponseData = { ok: true; runId: string; path: string; text: string; bytes: number } | { ok: false; error: string };
export default function ArtifactViewer({ runId, path, onClose, unavailableReason }: { runId: string; path: string; onClose: () => void; unavailableReason?: string }) {
  const [data, setData] = useState<ResponseData | null>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  const dialog = useRef<HTMLElement>(null);
  useEffect(() => {
    if (unavailableReason) { setData({ ok: false, error: unavailableReason }); return; }
    const controller = new AbortController();
    let active = true;
    setData(null);
    fetch(`/dev/evidence/${encodeURIComponent(runId)}?path=${encodeURIComponent(path)}`, { signal: controller.signal })
      .then(async (response) => await response.json() as ResponseData)
      .then((body) => { if (active) setData(body); })
      .catch(() => { if (active) setData({ ok: false, error: 'Evidence unavailable' }); });
    return () => { active = false; controller.abort(); };
  }, [runId, path, unavailableReason]);
  useEffect(() => {
    closeButton.current?.focus();
    const key = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); onClose(); }
      if (event.key === 'Tab') {
        const controls = dialog.current?.querySelectorAll<HTMLElement>('button:not(:disabled), [tabindex="0"]');
        if (!controls?.length) return;
        const first = controls[0], last = controls[controls.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    };
    window.addEventListener('keydown', key);
    return () => window.removeEventListener('keydown', key);
  }, [onClose]);
  return <div className={styles.backdrop}>
    <section ref={dialog} role="dialog" aria-modal="true" aria-label={`Artifact evidence: ${path}`} className={styles.dialog}>
      <header className={styles.header}><div><h2>Artifact evidence</h2><p>{runId} · {path}</p></div><button ref={closeButton} type="button" aria-label="Close artifact viewer" onClick={onClose}>Close</button></header>
      {data === null ? <p role="status">Loading evidence…</p> : data.ok ? <><pre className={styles.content} tabIndex={0} aria-label="Artifact source content">{data.text}</pre><p className={styles.note}>Fixture evidence · read-only observation · no qualification or authority granted.</p></> : <p role="status">Unavailable: {data.error}</p>}
    </section>
  </div>;
}
