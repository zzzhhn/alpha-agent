import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { GUIDE, GUIDE_SOURCES } from "./content";
import { guideTopics, searchGuideTopics, selectedGuideTopic } from "./guide-navigation";
import { UserGuide } from "./UserGuide";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

describe("guide navigation", () => {
  it("keeps all topics reachable by chapter and chooses a valid focused topic", () => {
    expect(GUIDE.flatMap(({ id }) => guideTopics(id)).map(({ entry }) => entry))
      .toEqual(GUIDE.flatMap(({ entries }) => entries));
    const routine = guideTopics("routine");
    expect(selectedGuideTopic(routine, "paper")?.entry.id).toBe("paper");
    expect(selectedGuideTopic(routine, "purpose")?.entry.id).toBe("weekly");
    expect(selectedGuideTopic(guideTopics("missing"), "paper")).toBeUndefined();
  });

  it("searches both languages across chapters, including titles and steps", () => {
    expect(searchGuideTopics("  DECISION ROUTINE ")).toEqual(guideTopics("routine"));
    expect(searchGuideTopics("借贷资金").map(({ entry }) => entry.id)).toContain("investing-income");
    expect(searchGuideTopics("  SELF-CORRELATION ").map(({ entry }) => entry.id)).toContain("correlation");
    expect(searchGuideTopics("")).toEqual([]);
    expect(searchGuideTopics("does not exist qzx")).toEqual([]);
  });

  it("opens on one article, with chapter semantics and all source links", () => {
    const html = renderToStaticMarkup(<UserGuide />);
    expect(html.match(/<article\b/g)).toHaveLength(1);
    expect(html).toContain('<h2 id="guide-article-title"');
    expect(html).toContain('aria-controls="guide-chapter-panel-start"');
    expect(html).toContain('id="guide-chapter-panel-start" role="tabpanel"');
    expect(html).toContain('aria-current="true" aria-controls="guide-article"');
    expect(html).not.toContain("真正收益来自你在券商账户");
    for (const source of GUIDE_SOURCES) expect(html).toContain(`href="${source.href}"`);
  });
});
