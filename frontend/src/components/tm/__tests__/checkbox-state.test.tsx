import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { TmCheckbox } from "../TmField";

describe("checkbox selected appearance", () => {
  it.each([true, false])("uses one background and border state when checked=%s", (checked) => {
    const html = renderToStaticMarkup(<TmCheckbox checked={checked} onChange={() => {}} label="定时" />);
    const mark = html.match(/<span aria-hidden="true" class="([^"]+)"/)!;
    const classes = mark[1].split(" ");
    expect(classes.filter((name) => name.startsWith("bg-"))).toEqual([checked ? "bg-tm-accent" : "bg-tm-bg"]);
    expect(classes.filter((name) => name.startsWith("border-tm-"))).toEqual([checked ? "border-tm-accent" : "border-tm-rule-2"]);
    expect(html.includes("✓")).toBe(checked);
  });
});
