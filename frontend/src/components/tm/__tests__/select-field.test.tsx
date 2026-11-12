import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { TmSelect } from "../TmField";
import { TmPagination } from "../TmPagination";

const noop = () => {};

describe("TmSelect uses the design-system listbox", () => {
  it("renders a labelled TmSelectMenu trigger instead of a native select", () => {
    const html = renderToStaticMarkup(
      <TmSelect id="sector" label="板块" hint="按板块筛选" value="it" onChange={noop}
        options={[{ value: "", label: "全部板块" }, { value: "it", label: "信息技术 · 73" }]} />,
    );
    expect(html).not.toContain("<select");
    expect(html).not.toContain("<option");
    expect(html).toContain('for="sector"');
    expect(html).toMatch(/<button id="sector"[^>]*aria-describedby="sector-hint"[^>]*aria-haspopup="listbox"/);
    expect(html).toContain("信息技术 · 73");
  });

  it("keeps aria-label, disabled and error semantics", () => {
    const html = renderToStaticMarkup(
      <TmSelect id="f" aria-label="按板块筛选" value="" onChange={noop} disabled error="无效"
        options={[{ value: "", label: "全部板块" }]} />,
    );
    expect(html).toMatch(/<button[^>]*disabled=""[^>]*aria-label="按板块筛选"[^>]*data-invalid="true"/);
    expect(html).toContain("border-tm-neg");
    expect(html).toContain('aria-describedby="f-error"');
  });

  it("pagination page size uses the same listbox", () => {
    const html = renderToStaticMarkup(
      <TmPagination page={1} pageSize={10} totalItems={40} pageSizeOptions={[10, 25]} onPageChange={noop} onPageSizeChange={noop}
        labels={{ navigation: "分页", previous: "上一页", previousAriaLabel: "上一页", next: "下一页", nextAriaLabel: "下一页",
          page: (c, t) => `${c} / ${t}`, pageSize: "每页", total: (n) => `共 ${n} 条` }} />,
    );
    expect(html).not.toContain("<select");
    expect(html).toMatch(/aria-label="每页"[^>]*aria-haspopup="listbox"/);
  });
});
