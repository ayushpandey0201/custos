import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

/* -----------------------------------------------------------------------------
 * A guided walkthrough: dims the page, spotlights one element at a time, and
 * explains it. Built in, no dependency: it only needs to find elements, scroll
 * to them and measure them.
 *
 * Steps point at elements by their `data-tour` name (or a CSS selector that
 * starts with # . or [). A step whose element is not on the page right now —
 * a result that has not appeared yet, a panel shown only when connected — is
 * skipped rather than pointing at nothing.
 * -------------------------------------------------------------------------- */

export interface TourStep {
  target?: string;
  title: string;
  body: string;
}

const PAD = 10;
const POP_W = 380;
// Clear of the sticky site header when scrolling a target into view.
const TOP_GAP = 92;

function find(target?: string): HTMLElement | null {
  if (!target) return null;
  const selector = /^[#.[]/.test(target) ? target : `[data-tour="${target}"]`;
  return document.querySelector<HTMLElement>(selector);
}

export function Tour({ steps, onClose }: { steps: TourStep[]; onClose: () => void }) {
  // Resolved once, when the tour opens: the steps that have something to show.
  const active = useMemo(() => steps.filter((s) => !s.target || find(s.target)), [steps]);
  const [index, setIndex] = useState(0);
  const [rect, setRect] = useState<DOMRect | null>(null);
  const [popH, setPopH] = useState(300);
  const popRef = useRef<HTMLDivElement>(null);
  const step = active[index];
  const last = index === active.length - 1;

  const measure = useCallback(() => {
    const el = find(step?.target);
    setRect(el ? el.getBoundingClientRect() : null);
  }, [step]);

  useLayoutEffect(() => {
    const el = find(step?.target);
    if (el) {
      // Put the target just under the header, leaving the rest of the screen
      // for the explanation. "instant", not smooth: the site sets
      // scroll-behavior: smooth on <html>, and a smooth scroll only advances
      // while the tab paints — on a slow projector laptop the guide would
      // point at the old position until it caught up. The spotlight animates.
      const top = window.scrollY + el.getBoundingClientRect().top - TOP_GAP;
      window.scrollTo({ top: Math.max(0, top), behavior: "instant" as ScrollBehavior });
    }
    measure();
    // Re-measure as late layout (fonts, images, data) settles.
    const timers = [80, 250, 600].map((ms) => window.setTimeout(measure, ms));
    return () => timers.forEach(clearTimeout);
  }, [step, measure]);

  useEffect(() => {
    window.addEventListener("scroll", measure, true);
    window.addEventListener("resize", measure);
    return () => {
      window.removeEventListener("scroll", measure, true);
      window.removeEventListener("resize", measure);
    };
  }, [measure]);

  const go = useCallback(
    (delta: number) => {
      const next = index + delta;
      if (next < 0) return;
      if (next >= active.length) onClose();
      else setIndex(next);
    },
    [index, active.length, onClose],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      else if (e.key === "ArrowRight" || e.key === "Enter") {
        e.preventDefault();
        go(1);
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        go(-1);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [go, onClose]);

  useLayoutEffect(() => {
    if (popRef.current) setPopH(popRef.current.offsetHeight);
  }, [step, rect]);

  if (!step) return null;

  const vw = window.innerWidth;
  const vh = window.innerHeight;

  // Spotlight, clamped to the viewport so a tall element still reads as "this".
  const spotTop = rect ? Math.min(Math.max(6, rect.top - PAD), vh - 60) : 0;
  const spot = rect
    ? {
        left: Math.max(6, rect.left - PAD),
        top: spotTop,
        width: Math.min(vw - 12, rect.width + PAD * 2),
        height: Math.max(40, Math.min(vh - 6 - spotTop, rect.bottom + PAD - spotTop)),
      }
    : null;

  // Popover: below the spotlight if it fits, else above, else pinned at the
  // bottom of the screen over the element.
  let pop: React.CSSProperties;
  if (!spot) {
    pop = { left: (vw - POP_W) / 2, top: Math.max(12, (vh - popH) / 2) };
  } else {
    const left = Math.min(Math.max(12, spot.left + 12), vw - POP_W - 12);
    const below = spot.top + spot.height + 14;
    const sideTop = Math.min(Math.max(12, spot.top), vh - popH - 12);
    if (spot.width < vw * 0.45 && spot.left - POP_W - 14 >= 12) {
      // A narrow column (a side panel): explain it from beside, not on top.
      pop = { left: spot.left - POP_W - 14, top: sideTop };
    } else if (spot.width < vw * 0.45 && spot.left + spot.width + 14 + POP_W <= vw - 12) {
      pop = { left: spot.left + spot.width + 14, top: sideTop };
    } else if (below + popH <= vh - 12) pop = { left, top: below };
    else if (spot.top - 14 - popH >= 12) pop = { left, top: spot.top - 14 - popH };
    // Taller than the screen allows: sit over the lower part of the target.
    else pop = { right: 24, bottom: 18 };
  }

  return (
    <div className="tour" role="dialog" aria-modal="true" aria-label={`Guide: ${step.title}`}>
      <div className="tour-block" onClick={(e) => e.stopPropagation()} />
      {spot ? <div className="tour-spot" style={spot} /> : <div className="tour-dim" />}
      <div className="tour-pop" ref={popRef} style={{ ...pop, width: POP_W }}>
        <div className="tour-count">
          Guide · {index + 1} of {active.length}
          <button className="tour-x" onClick={onClose} aria-label="Close the guide">×</button>
        </div>
        <h3 className="tour-title">{step.title}</h3>
        <p className="tour-body">{step.body}</p>
        <div className="tour-dots" aria-hidden="true">
          {active.map((_, i) => (
            <span key={i} className={`tour-dot ${i === index ? "is-on" : i < index ? "is-past" : ""}`} />
          ))}
        </div>
        <div className="tour-actions">
          <button className="btn" onClick={() => go(-1)} disabled={index === 0}>
            ← Back
          </button>
          <span className="tour-keys">← → or Enter · Esc to close</span>
          <button className="btn btn-primary" onClick={() => go(1)} autoFocus>
            {last ? "Finish" : "Next →"}
          </button>
        </div>
      </div>
    </div>
  );
}

/** The always-available launcher. Glows on pages this browser has not toured yet. */
export function TourButton({ seen, onClick }: { seen: boolean; onClick: () => void }) {
  return (
    <button className={`tour-launch ${seen ? "" : "is-new"}`} onClick={onClick} title="Walk me through this page">
      <span className="tour-launch-icon" aria-hidden="true">?</span>
      <span>{seen ? "Guide me" : "New here? Take the tour"}</span>
    </button>
  );
}
