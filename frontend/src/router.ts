import { useEffect, useState } from "react";

// Three routes, so a tiny router instead of a dependency (AGENTS.md §2).
export function navigate(to: string): void {
  history.pushState(null, "", to);
  dispatchEvent(new PopStateEvent("popstate"));
  scrollTo(0, 0);
}

export function usePath(): string {
  const [path, setPath] = useState(location.pathname);
  useEffect(() => {
    const on = () => setPath(location.pathname);
    addEventListener("popstate", on);
    return () => removeEventListener("popstate", on);
  }, []);
  return path;
}
