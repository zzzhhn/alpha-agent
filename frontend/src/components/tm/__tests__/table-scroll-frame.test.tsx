import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { TmTable, TmTableFrame } from "../TmTable";

describe("table scroll frame", () => {
  it("contains positioned accessibility text without removing it", () => {
    const html = renderToStaticMarkup(
      <TmTableFrame>
        <TmTable caption="候选明细">
          <tbody><tr><td><span className="sr-only">近五日：</span>52%</td></tr></tbody>
        </TmTable>
      </TmTableFrame>,
    );
    expect(html).toContain('class="relative min-w-0 overflow-x-auto"');
    expect(html).toContain('<caption class="sr-only">候选明细</caption>');
    expect(html).toContain('<span class="sr-only">近五日：</span>');
  });
});
