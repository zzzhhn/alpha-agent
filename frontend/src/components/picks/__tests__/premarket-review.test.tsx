import { renderToStaticMarkup } from "react-dom/server";
import { expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import PremarketReview from "../PremarketReview";

const state=vi.hoisted(()=>({admin:true}));
vi.mock("@/components/layout/SystemHealth",()=>({useAdminAccess:()=>state.admin}));
vi.mock("@/components/research/ForwardEvidence",()=>({
  Fold:({title,children}:{title:string;children:ReactNode})=><section>{title}{children}</section>,
  Read:({children}:{children:(v:unknown)=>ReactNode})=>children({
    summary:{observed_closes:0,stages:{}},records:[{session_date:"2026-11-25",stage:"open_review",
      captured_at:"2026-11-25T15:01:00Z",payload:{run_id:89,comparable:true,tracked:3,recent:2,
        top_covered:2,notes:[{ticker:"ABC",tag:"review",held:true}],changes:[],
        events:[],context:[],quotes:{ABC:null}}}],
  }),
}));
it("renders coverage, unchanged ranks and unavailable quotes without showing private records to guests",()=>{
  const html=renderToStaticMarkup(<PremarketReview/>);
  for(const s of ["10:00 ET","Top 50","2/50","ABC","无新鲜报价","影子组合保持正式榜不变","机器人持仓"])expect(html).toContain(s);
  state.admin=false;
  expect(renderToStaticMarkup(<PremarketReview/>)).toBe("");
});
