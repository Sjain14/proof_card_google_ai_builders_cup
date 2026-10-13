import type { Verdict } from "../api";
import { VERDICT } from "../verdict";

export function VerdictPill({ verdict, hindi = false }: { verdict: Verdict; hindi?: boolean }) {
  const v = VERDICT[verdict];
  return (
    <span className={`pill ${v.cls}`}>
      <span aria-hidden="true">{v.icon}</span> {v.en}
      {hindi && <span className="pill-hi">{v.hi}</span>}
    </span>
  );
}
