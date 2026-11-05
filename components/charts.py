"""
统一的 Plotly 图表样式。

所有图表共用同一套低饱和配色、字体、网格线与留白，避免各页面各写一份
layout 配置导致视觉不一致。本模块只负责"外观"，不改变任何数据、指标
口径或统计逻辑——调用方仍然传入原始数据序列。

配色约定：
    - 折线/柱状图只使用主色及其低饱和衍生色，不出现彩虹色；
    - 饼图用同色系明度阶梯表示同一维度的不同等级（如高/中/低风险）；
    - 网格线极浅且只保留横向，坐标轴无轴线、无箭头。
"""

from __future__ import annotations

from typing import Sequence

from config.theme import (
    COLOR_BORDER,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_SECONDARY,
    COLOR_TEXT,
    FONT_STACK,
    font_scale,
)


def _font_size(base_px: float, scale: float) -> float:
    return round(base_px * scale, 1)


def _base_layout(scale: float, height: int) -> dict:
    return {
        "height": height,
        "margin": {"l": 8, "r": 8, "t": 8, "b": 8},
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "font": {
            "family": FONT_STACK,
            "size": _font_size(12, scale),
            "color": COLOR_TEXT_SECONDARY,
        },
        "hoverlabel": {
            "bgcolor": "#FFFFFF",
            "bordercolor": COLOR_BORDER,
            "font": {"family": FONT_STACK, "size": _font_size(12, scale), "color": COLOR_TEXT},
        },
        "showlegend": False,
        "hovermode": "x unified",
    }


def _axis(scale: float, *, show_grid: bool = True) -> dict:
    return {
        "showgrid": show_grid,
        "gridcolor": COLOR_BORDER,
        "gridwidth": 1,
        "zeroline": False,
        "showline": False,
        "ticks": "",
        "tickfont": {"size": _font_size(11, scale), "color": COLOR_TEXT_MUTED},
        "title": {"font": {"size": _font_size(11, scale), "color": COLOR_TEXT_MUTED}},
        "automargin": True,
    }


def line_chart(
    x: Sequence,
    y: Sequence,
    *,
    primary: str,
    x_title: str = "",
    y_title: str = "",
    height: int = 260,
    font_size_key: str = "medium",
) -> "object":
    """单序列折线图：细线 + 小圆点，无填充、无图例。"""
    import plotly.graph_objects as go

    scale = font_scale(font_size_key)
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=list(x),
            y=list(y),
            mode="lines+markers",
            line={"color": primary, "width": 2, "shape": "linear"},
            marker={"size": 4, "color": primary, "line": {"width": 0}},
            hovertemplate="%{x} · %{y}<extra></extra>",
        )
    )
    layout = _base_layout(scale, height)
    layout["xaxis"] = {**_axis(scale, show_grid=False), "title": {"text": x_title, "font": {"size": _font_size(11, scale), "color": COLOR_TEXT_MUTED}}}
    layout["yaxis"] = {**_axis(scale), "title": {"text": y_title, "font": {"size": _font_size(11, scale), "color": COLOR_TEXT_MUTED}}}
    layout["hovermode"] = "x"
    fig.update_layout(**layout)
    return fig


def bar_chart(
    x: Sequence,
    y: Sequence,
    *,
    primary: str,
    height: int = 260,
    font_size_key: str = "medium",
) -> "object":
    """单序列柱状图：低饱和主色、无边框、柱间细窄间隙。"""
    import plotly.graph_objects as go

    scale = font_scale(font_size_key)
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=list(x),
            y=list(y),
            marker={"color": primary, "line": {"width": 0}},
            opacity=0.9,
            hovertemplate="%{x} · %{y}<extra></extra>",
        )
    )
    layout = _base_layout(scale, height)
    layout["xaxis"] = {**_axis(scale, show_grid=False), "title": {"text": ""}}
    layout["yaxis"] = {**_axis(scale), "title": {"text": ""}}
    layout["bargap"] = 0.55
    layout["hovermode"] = "closest"
    fig.update_layout(**layout)
    return fig


def donut_chart(
    labels: Sequence[str],
    values: Sequence[int],
    *,
    palette: Sequence[str],
    height: int = 260,
    font_size_key: str = "medium",
) -> "object":
    """环形图：单色系明度阶梯，标签以图例形式紧凑排列。"""
    import plotly.graph_objects as go

    scale = font_scale(font_size_key)
    fig = go.Figure(
        go.Pie(
            labels=list(labels),
            values=list(values),
            hole=0.62,
            sort=False,
            marker={"colors": list(palette), "line": {"color": "#FFFFFF", "width": 2}},
            textinfo="none",
            hovertemplate="%{label} · %{value}<extra></extra>",
        )
    )
    layout = _base_layout(scale, height)
    layout["showlegend"] = True
    layout["legend"] = {
        "orientation": "v",
        "x": 1.0,
        "xanchor": "right",
        "y": 0.5,
        "yanchor": "middle",
        "font": {"size": _font_size(12, scale), "color": COLOR_TEXT_SECONDARY},
        "itemclick": False,
        "itemdoubleclick": False,
        "bgcolor": "rgba(0,0,0,0)",
    }
    layout["margin"] = {"l": 0, "r": 0, "t": 8, "b": 8}
    fig.update_layout(**layout)
    return fig


def severity_palette(error: str, warning: str, success: str) -> tuple[str, ...]:
    """高/中/低风险的环形图配色：同色系阶梯，保持语义可读。"""
    return (error, warning, success)


def plotly_config() -> dict:
    """统一的 Plotly 交互配置：去掉非必要工具栏按钮，保留悬停与保存。"""
    return {
        "displaylogo": False,
        "modeBarButtonsToRemove": [
            "select2d",
            "lasso2d",
            "autoScale2d",
            "toggleSpikelines",
            "hoverClosestCartesian",
            "hoverCompareCartesian",
        ],
        "responsive": True,
    }
