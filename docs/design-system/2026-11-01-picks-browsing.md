# 候选明细浏览与证据说明

## 边界

任务：桌面用户比较候选并判断数据可靠性。保留 AlphaCore 颜色、字体、TM 控件、候选排序、所有数据及统计口径；精修列表导航和证据说明。不改后端、不引入动画依赖、不增加数据库请求。

## 参考选择（2026-11-01）

以下为官方文档观察，不宣称已操作参考产品全部交互。

| 模式 | 证据 | 决策与本项目落点 |
| --- | --- | --- |
| 数据分页、范围和总数 | [Carbon Data table](https://www.carbondesignsystem.com/building-blocks/core/components/data-table/guidelines)、[Pagination](https://www.carbondesignsystem.com/building-blocks/core/components/pagination/guidelines) | 复用 TmPagination，默认 10 条，提供 25/50；全局排名跨页连续，搜索/快照改变回第一页。 |
| 短 tooltip，长说明点击打开 | [Carbon Tooltip](https://carbondesignsystem.com/components/tooltip/usage/) | 移除整块数值上的长 hover；用既有 TmDialog 展示四窗口、样本门槛和口径。重要缺数继续留在行内。 |
| 有功能目的的进入/退出 | [Fluent Motion](https://fluent2.microsoft.design/motion) | 翻页采用 160ms 的小幅位移淡入，仅提示列表切换；尊重 prefers-reduced-motion。 |
| 列表弹簧入场和滑动选择 | [React Bits Animated List](https://reactbits.dev/components/animated-list) | 只采纳保持浏览方位的思路，拒绝金融数据逐行弹跳、数值补间、滚动劫持与新动画依赖。 |

## 实施与验收

- 使用已有 TmTableFrame、TmPagination、TmButton、TmDialog、TmDisclosureButton，沿用表格定位边界修复。
- 限高表格区域、固定表头；翻页复位局部滚动，不移动外部页面或焦点。分页控制在数据区外，切换时位置稳定。
- 固定列维度和信号新鲜度按全量结果计算，不因当前页改变。候选总数与完整排名保持不变。
- 证据详情分为方向统计、两项不同含义的模型指标、可展开的 HOLD 补充口径；不把缺失值或未知样本记成零。
- 验证 1/2/末页、25/50 条、搜索清除、空结果、键盘关闭与焦点返回、深浅/中英、读屏文本、动态效果降级、根文档无额外滚动。

## 本地结果

- TypeScript、3 个相关测试文件共 8 项测试、设计系统审计通过。
- 使用生产公共快照的只读夹具检查：第一页 10 条，第二页 11 至 20，末页 41 至 50，末页下一页禁用；25/50 条切换正确。
- 50 条模式滚动至底部，表头保持固定；根文档额外滚动高度为 0。
- 在第二页搜索 NVDA 后为 1 条且回到第一页；无匹配时展示空态，清除搜索后恢复完整 50 条、第一页。
- 证据窗口、HOLD 展开、Esc 关闭、焦点返回均通过；英文深色及中文浅色窗口未见裁切。
- 已在浏览器观察到翻页动画；减少动态效果通过 CSS 分支核验，未修改系统偏好模拟。

线上部署和最终浏览器验收以本轮发布回执为准。
