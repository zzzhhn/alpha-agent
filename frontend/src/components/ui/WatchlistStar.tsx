import { Star } from "lucide-react";

// Small filled star marking a ticker that is in the user's watchlist.
// Rendered next to the ticker symbol wherever tickers appear so watchlist
// names stand out from the rest. Pairs with the useWatchlist hook.
export default function WatchlistStar({ className }: { className?: string }) {
  return (
    <Star
      aria-label="In watchlist"
      className={className ?? "inline-block h-3 w-3 align-middle text-tm-accent"}
      fill="currentColor"
      strokeWidth={1.75}
    />
  );
}
