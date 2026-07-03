import { fetchBrainAlphas, type BrainAlpha } from "@/lib/api/brain";
import { BrainMiningPanel } from "@/components/brain/BrainMiningPanel";

// Phase E5: the WorldQuant BRAIN mining review page. Fetches the user's mined
// alphas server-side (degrades to an empty list if the backend/table isn't
// ready) and hands them to the client panel that renders buckets + submit.
export default async function BrainPage() {
  let alphas: BrainAlpha[] = [];
  try {
    const res = await fetchBrainAlphas(100, {
      revalidate: 0,
      tags: ["brain-alphas"],
    });
    alphas = res.alphas;
  } catch {
    alphas = [];
  }
  return <BrainMiningPanel alphas={alphas} />;
}
