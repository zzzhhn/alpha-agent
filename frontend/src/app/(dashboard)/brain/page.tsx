import { BrainMiningPanel } from "@/components/brain/BrainMiningPanel";

// Phase E5: the WorldQuant BRAIN mining review page. The panel fetches the
// user's mined alphas CLIENT-side — /api/brain/alphas is auth-gated, and SSR
// server-component fetches skip the Next.js middleware that injects the auth
// token (so a server-side fetch would 401 → "no results" even with data).
export default function BrainPage() {
  return <BrainMiningPanel />;
}
