import { useEffect, useState } from "react";
import { Tour, TourButton } from "./components/Tour";
import { TOURS } from "./components/tours";
import { AgentDemo } from "./views/AgentDemo";
import { Console } from "./views/Console";
import { Docs } from "./views/Docs";
import { GuidedDemo } from "./views/GuidedDemo";
import { Healing } from "./views/Healing";
import { Home } from "./views/Home";

const CONTROL_URL = import.meta.env.VITE_CONTROL_URL ?? "http://localhost:8001";
const STORAGE_KEY = "custos.apiKey";

type Route = "home" | "demo" | "healing" | "agent" | "docs" | "console";

const ROUTES: Route[] = ["home", "demo", "healing", "agent", "docs", "console"];
const DEMO_ROUTES: Route[] = ["demo", "healing", "agent"];

const NAV: { route: Route; label: string }[] = [
  { route: "home", label: "Why Custos" },
  { route: "demo", label: "Live demos" },
  { route: "docs", label: "Documentation" },
  { route: "console", label: "Console" },
];

const TOUR_SEEN_KEY = "custos.toursSeen";

/** Hash routing: no router dependency, and a refresh keeps you where you were. */
function readRoute(): Route {
  const hash = window.location.hash.replace(/^#\/?/, "");
  return (ROUTES.find((r) => r === hash) ?? "home") as Route;
}

function readSeen(): string[] {
  try {
    return JSON.parse(localStorage.getItem(TOUR_SEEN_KEY) ?? "[]");
  } catch {
    return [];
  }
}

function Logo() {
  return (
    <svg viewBox="0 0 32 32" className="logo" aria-hidden="true">
      <defs>
        <linearGradient id="lg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#7cc4ff" />
          <stop offset="1" stopColor="#a78bfa" />
        </linearGradient>
      </defs>
      <path d="M16 2 4 7v8c0 7.4 5.1 13.4 12 15 6.9-1.6 12-7.6 12-15V7L16 2Z" fill="url(#lg)" />
      <path d="m10.5 16 4 4 7-8" fill="none" stroke="#0b1020" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function App() {
  const [route, setRoute] = useState<Route>(readRoute);
  const [apiKey, setApiKeyState] = useState(() => localStorage.getItem(STORAGE_KEY) ?? "");
  const [touring, setTouring] = useState(false);
  const [seen, setSeen] = useState<string[]>(readSeen);

  useEffect(() => {
    const onHash = () => {
      setTouring(false);
      setRoute(readRoute());
      window.scrollTo({ top: 0 });
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const setApiKey = (key: string) => {
    if (key) localStorage.setItem(STORAGE_KEY, key);
    else localStorage.removeItem(STORAGE_KEY);
    setApiKeyState(key);
  };

  return (
    <div className="site">
      <header className="nav">
        <a className="brand" href="#/home">
          <Logo />
          <span className="brand-name">Custos</span>
          <span className="brand-tag">runtime trust layer</span>
        </a>
        <nav className="nav-links">
          {NAV.map((n) => (
            <a
              key={n.route}
              href={`#/${n.route}`}
              className={`nav-link ${route === n.route || (n.route === "demo" && DEMO_ROUTES.includes(route)) ? "is-active" : ""}`}
            >
              {n.label}
            </a>
          ))}
        </nav>
        <a className="btn btn-primary nav-cta" href="#/demo">Start demos</a>
      </header>

      <main className="site-main">
        {route === "home" && <Home />}
        {route === "demo" && <GuidedDemo controlUrl={CONTROL_URL} onKey={setApiKey} />}
        {route === "healing" && <Healing controlUrl={CONTROL_URL} apiKey={apiKey} onKey={setApiKey} />}
        {route === "agent" && <AgentDemo controlUrl={CONTROL_URL} onKey={setApiKey} />}
        {route === "docs" && <Docs />}
        {route === "console" && <Console controlUrl={CONTROL_URL} apiKey={apiKey} setApiKey={setApiKey} />}
      </main>

      <TourButton
        seen={seen.includes(route)}
        onClick={() => {
          setTouring(true);
          if (!seen.includes(route)) {
            const next = [...seen, route];
            setSeen(next);
            localStorage.setItem(TOUR_SEEN_KEY, JSON.stringify(next));
          }
        }}
      />
      {touring && <Tour key={route} steps={TOURS[route] ?? []} onClose={() => setTouring(false)} />}

      <footer className="footer">
        <span>
          <b>Custos</b> · Project Work Phase-II (23AI7PWPP1) · Dept. of AI &amp; DS, BMS College of Engineering
        </span>
        <span className="muted">Ayush Pandey · Vivek Boora · Nitin — guided by Dr. Seemanthini K G</span>
      </footer>
    </div>
  );
}
