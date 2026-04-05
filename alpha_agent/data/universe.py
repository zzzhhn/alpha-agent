"""Stock universe definitions for A-share backtesting."""

from __future__ import annotations

# fmt: off
# Top-50 CSI 300 constituents by market cap (6-digit AKShare codes).
# Snapshot as of 2026-Q1 — update periodically.
_CSI300_TOP50: dict[str, str] = {
    "600519": "贵州茅台",
    "601318": "中国平安",
    "600036": "招商银行",
    "601012": "隆基绿能",
    "000858": "五粮液",
    "600900": "长江电力",
    "000333": "美的集团",
    "601166": "兴业银行",
    "600276": "恒瑞医药",
    "601398": "工商银行",
    "600309": "万华化学",
    "000001": "平安银行",
    "600030": "中信证券",
    "601888": "中国中免",
    "000002": "万科A",
    "600809": "山西汾酒",
    "002475": "立讯精密",
    "601288": "农业银行",
    "300750": "宁德时代",
    "000568": "泸州老窖",
    "002714": "牧原股份",
    "600050": "中国联通",
    "601668": "中国建筑",
    "600585": "海螺水泥",
    "601857": "中国石油",
    "000725": "京东方A",
    "601328": "交通银行",
    "600887": "伊利股份",
    "002304": "洋河股份",
    "601225": "陕西煤业",
    "600000": "浦发银行",
    "002352": "顺丰控股",
    "600028": "中国石化",
    "601601": "中国太保",
    "000651": "格力电器",
    "002594": "比亚迪",
    "601919": "中远海控",
    "600031": "三一重工",
    "002415": "海康威视",
    "601088": "中国神华",
    "600104": "上汽集团",
    "600690": "海尔智家",
    "601211": "国泰君安",
    "600048": "保利发展",
    "601939": "建设银行",
    "002142": "宁波银行",
    "600588": "用友网络",
    "003816": "中国广核",
    "601899": "紫金矿业",
    "600436": "片仔癀",
}
# fmt: on


class CSI300Universe:
    """Provides the investable universe for backtesting.

    Currently hardcoded to the top-50 CSI 300 constituents by market cap.
    """

    @property
    def stock_codes(self) -> list[str]:
        """Return a list of 6-digit stock codes."""
        return list(_CSI300_TOP50.keys())

    def name_map(self) -> dict[str, str]:
        """Return an immutable copy of code -> Chinese name mapping."""
        return dict(_CSI300_TOP50)

    def __len__(self) -> int:
        return len(_CSI300_TOP50)

    def __repr__(self) -> str:
        return f"CSI300Universe(n={len(self)})"
