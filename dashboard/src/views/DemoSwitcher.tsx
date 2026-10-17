/* The three live demos as one presenting sequence.
 *
 * Shown at the top of every demo page so the presenter always knows where they
 * are in the running order, and at the end of each demo as "Next demo". */

export type DemoId = "demo" | "healing" | "agent";

export const DEMOS: { id: DemoId; title: string; domain: string; minutes: number; pitch: string }[] = [
  {
    id: "demo",
    title: "The trust gate",
    domain: "Lending",
    minutes: 4,
    pitch: "A model drifts; Custos stops trusting it — and catches someone editing the evidence.",
  },
  {
    id: "healing",
    title: "Self-healing",
    domain: "Lending",
    minutes: 3,
    pitch: "A data feed breaks; Custos diagnoses it and repairs it once a person approves.",
  },
  {
    id: "agent",
    title: "AI agent guardrail",
    domain: "E-commerce",
    minutes: 3,
    pitch: "An AI agent issuing refunds loops, gets talked into a bad refund, meets a fraud ring.",
  },
];

export function DemoSwitcher({ current }: { current: DemoId }) {
  return (
    <nav className="demo-switcher" aria-label="Live demos" data-tour="switcher">
      {DEMOS.map((d, i) => (
        <a key={d.id} href={`#/${d.id}`} className={`switch-item ${current === d.id ? "is-current" : ""}`}>
          <span className="switch-num">{i + 1}</span>
          <span className="switch-text">
            <span className="switch-title">
              {d.title} <span className="switch-domain">{d.domain}</span>
            </span>
            <span className="switch-pitch">{d.pitch}</span>
          </span>
          <span className="switch-min">{d.minutes} min</span>
        </a>
      ))}
    </nav>
  );
}

/** "Next demo →", or a pointer to the console after the last one. */
export function NextDemo({ current }: { current: DemoId }) {
  const index = DEMOS.findIndex((d) => d.id === current);
  const next = DEMOS[index + 1];
  if (!next) {
    return (
      <a className="btn btn-primary" href="#/console">
        All three done — open the operator console →
      </a>
    );
  }
  return (
    <a className="btn btn-primary" href={`#/${next.id}`}>
      Next demo: {next.title} ({next.domain}) →
    </a>
  );
}
