import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import OnboardingBanner from "../OnboardingBanner";

// Seed only the banner's post-mount dismiss state for static rendering; no DOM.
const state = vi.hoisted(() => ({ show: true, hasKey: false, loading: false }));
vi.mock("react", async (original) => {
  const react = await original<typeof import("react")>();
  return { ...react, useState: (initial: unknown) => react.useState(initial === false ? state.show : initial) };
});
vi.mock("@/hooks/useHasByok", () => ({ useHasByok: () => ({ hasKey: state.hasKey, loading: state.loading }) }));

beforeEach(() => { Object.assign(state, { show: true, hasKey: false, loading: false }); });

describe("onboarding visibility", () => {
  it("hides the banner for an existing server-side key", () => {
    state.hasKey = true;
    expect(renderToStaticMarkup(<OnboardingBanner />)).toBe("");
  });
  it("waits for the credential check to avoid flashing for configured users", () => {
    state.loading = true;
    expect(renderToStaticMarkup(<OnboardingBanner />)).toBe("");
  });
  it("preserves onboarding when no key is found or the hook falls back after an error", () => {
    const html = renderToStaticMarkup(<OnboardingBanner />);
    expect(html).toContain("欢迎使用 AlphaCore");
    expect(html).toContain('href="/settings"');
    expect(html).not.toContain("功能已就绪");
  });
  it("preserves the dismiss flag", () => {
    state.show = false;
    expect(renderToStaticMarkup(<OnboardingBanner />)).toBe("");
  });
});
