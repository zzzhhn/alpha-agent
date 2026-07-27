import PaperScreen from "@/components/picks/paper/PaperScreen";

// /paper — one recommendation-to-trade workspace. Legacy ?tab= links remain
// harmless because the server route ignores the obsolete query parameter.
export const dynamic = "force-dynamic";

export default function PaperPage() {
  return <PaperScreen />;
}
