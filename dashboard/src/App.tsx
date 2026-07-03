import { Models } from "./views/Models";
import { DriftMonitor } from "./views/DriftMonitor";
import { Decisions } from "./views/Decisions";
import { AuditLog } from "./views/AuditLog";

export function App() {
  return (
    <div>
      <Models />
      <DriftMonitor />
      <Decisions />
      <AuditLog />
    </div>
  );
}

