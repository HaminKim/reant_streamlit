# app_streamlit.py — MA on/off + 네임맵 + 즐겨찾기(저장) + 순매수/순매도 순위 + 조건 필터(20거래일) + 로고 표시
import json
import base64
import re
from pathlib import Path
import time

import streamlit.components.v1 as components
import pandas as pd
import streamlit as st
import altair as alt
from urllib.parse import quote_plus
from PIL import Image  # ✅ 로고 이미지 표시용

FONT_STACK = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, " \
"Noto Sans', 'Helvetica Neue', Arial, 'Apple SD Gothic Neo', 'Malgun Gothic', '맑은 고딕', " \
"'AppleGothic', 'Nanum Gothic', sans-serif"

st.set_page_config(page_title="리버스 개미 대시보드", layout="wide")

# ───────────────────────────
# 경로 설정
# ───────────────────────────
BASE_DIR = Path(__file__).parent
LOGO_DIR = BASE_DIR / "assets" / "logos"

PROC_DIR = BASE_DIR / "processed"
DATA_PATH = PROC_DIR / "all_data_clean.csv"
NAME_MAP_PATH = PROC_DIR / "name_map.csv"
FAV_PATH = PROC_DIR / "favorites.json"

def get_mtime(p: Path) -> float:
    """파일 수정시간(초). 없으면 0."""
    try:
        return p.stat().st_mtime
    except FileNotFoundError:
        return 0.0

def find_logo_path(stock_name: str):
    p = LOGO_DIR / f"{stock_name}.png"
    if p.exists():
        return p
    safe = stock_name.replace("/", "_").replace("\\", "_").replace(":", " ")
    p2 = LOGO_DIR / f"{safe}.png"
    return p2 if p2.exists() else None

# ✅ HTML 한 줄: 로고 + 종목명
def render_title_line(logo_path: str, sel_disp: str, size: int = 86, align: str = "center"):
    m = re.match(r'^(.*?)\s*\((.+)\)\s*$', sel_disp)
    has_korean = bool(m)

    if has_korean:
        korean  = (m.group(1) or "").strip()
        english = (m.group(2) or "").strip()
    else:
        korean  = None
        english = sel_disp.strip()

    logo_b64 = ""
    if logo_path:
        try:
            with open(logo_path, "rb") as f:
                logo_b64 = base64.b64encode(f.read()).decode()
        except Exception:
            logo_b64 = ""

    jc = {"left": "flex-start", "center": "center", "right": "flex-end"}.get(align, "center")

    # 텍스트(영문은 항상 14px, 볼드 X / 한글 26px Bold)
    if has_korean:
        text_html = f"""
            <div style="display:flex;align-items:baseline;gap:6px;flex-wrap:wrap;font-family:{FONT_STACK};">
                <span style="font-size:32px;font-weight:700;line-height:1;">{korean}</span>
                <span style="font-size:14px;font-weight:400;color:#666;line-height:1;">({english})</span>
            </div>
        """
    else:
        text_html = f"""
            <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;font-family:{FONT_STACK};">
                <span style="font-size:14px;font-weight:400;color:#222;line-height:1;">{english}</span>
            </div>
        """

    body = (
        f"""
        <div style="display:flex;align-items:center;justify-content:{jc};
                    gap:10px;margin:8px 0 10px 0;font-family:{FONT_STACK};">
            <img src="data:image/png;base64,{logo_b64}" width="{size}" height="{size}"
                 style="object-fit:contain;border-radius:8px;" />
            {text_html}
        </div>
        """
        if logo_b64 else
        f"""
        <div style="display:flex;align-items:center;justify-content:{jc};
                    gap:10px;margin:8px 0 10px 0;font-family:{FONT_STACK};">
            {text_html}
        </div>
        """
    )

    components.html(body, height=max(size, 26) + 28, scrolling=False)

# ───────────────────────────
# 즐겨찾기 저장/로드
# ───────────────────────────
def load_favorites() -> set:
    try:
        if FAV_PATH.exists():
            with open(FAV_PATH, "r", encoding="utf-8") as f:
                return set(json.load(f))
    except Exception:
        pass
    return set()

def save_favorites(favs: set):
    FAV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(FAV_PATH, "w", encoding="utf-8") as f:
        json.dump(sorted(list(favs)), f, ensure_ascii=False, indent=2)

def toggle_favorite(code: str):
    favs = st.session_state.get("favs", set())
    if code in favs:
        favs.remove(code)
    else:
        favs.add(code)
    st.session_state["favs"] = favs
    save_favorites(favs)

# ───────────────────────────
# 📂 데이터 불러오기 (자동 갱신)
# ───────────────────────────
@st.cache_data(ttl=600)  # ✅ 10분마다 자동 만료(보험)
def load_data(_data_mtime: float, _map_mtime: float):
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"데이터 파일이 없습니다: {DATA_PATH}")

    df = pd.read_csv(DATA_PATH, parse_dates=["날짜"], encoding="utf-8-sig")

    need_base = {"날짜", "종목명", "매수", "매도", "순매수"}
    miss_base = need_base - set(df.columns)
    if miss_base:
        raise ValueError(f"필수 컬럼 누락: {miss_base}")

    # MA 컬럼 없으면 생성(호환)
    for n in (5, 10, 20):
        col = f"MA{n}"
        if col not in df.columns:
            df[col] = (
                df.groupby("종목명")["순매수"]
                  .rolling(window=n, min_periods=n)
                  .mean()
                  .reset_index(level=0, drop=True)
            )

    # 네임맵(있으면 적용)
    try:
        if NAME_MAP_PATH.exists():
            name_map_df = pd.read_csv(NAME_MAP_PATH)
            if {"영문명", "한글명"} <= set(name_map_df.columns):
                name_map = dict(zip(name_map_df["영문명"], name_map_df["한글명"]))
                df["표시명"] = df["종목명"].map(name_map)
                df["표시명"] = df.apply(
                    lambda r: f"{r['표시명']} ({r['종목명']})" if pd.notna(r["표시명"]) else r["종목명"],
                    axis=1,
                )
            else:
                df["표시명"] = df["종목명"]
        else:
            df["표시명"] = df["종목명"]
    except Exception:
        df["표시명"] = df["종목명"]

    return df.sort_values(["종목명", "날짜"])

df = load_data(get_mtime(DATA_PATH), get_mtime(NAME_MAP_PATH))

if "favs" not in st.session_state:
    st.session_state["favs"] = load_favorites()

# ───────────────────────────
# 기본 설정
# ───────────────────────────
qp = st.query_params

min_date = df["날짜"].min().date()
max_date = df["날짜"].max().date()
default_start = max(min_date, pd.to_datetime("2025-01-01").date())
default_end   = max_date

def fmt_usd(x):
    try:
        return f"${x:,.0f}"
    except Exception:
        return "-"

def _set_date_slider(value_tuple):
    st.session_state["range_value"] = value_tuple
    st.session_state["range_slider"] = value_tuple

def _set_rank_slider(value_tuple):
    st.session_state["rank_range"] = value_tuple
    st.session_state["rank_range_slider"] = value_tuple

def compute_last_n_trading_days(stock: str, n: int):
    if not stock:
        return
    dts = (
        df.loc[df["종목명"] == stock, "날짜"]
          .dt.date.drop_duplicates().sort_values().tolist()
    )
    if not dts:
        _set_date_slider((default_start, default_end))
        return
    end = dts[-1]
    start = dts[-n] if len(dts) >= n else dts[0]
    _set_date_slider((start, end))

# ───────────────────────────
# ✅ TAB 5개
# ───────────────────────────
tab_names = ["📈 종목별 차트", "🏆 인기 종목 TOP50", "📊 순매수·순매도 순위", "🧪 조건 필터", "📘 소개/가이드"]
t_chart, t_top, t_rank, t_filter, t_guide = st.tabs(tab_names)

# ───────────────────────────
# 1) 📈 종목별 차트
# ───────────────────────────
with t_chart:
    st.markdown("### 📊 종목별 순매수 추이")

    stocks_disp = sorted(df["표시명"].dropna().unique().tolist())
    code_to_disp = (
        df[["종목명", "표시명"]]
        .drop_duplicates(subset=["종목명"])
        .set_index("종목명")["표시명"]
        .to_dict()
    )
    disp_to_code = {v: k for k, v in code_to_disp.items()}

    PLACEHOLDER = "🔎 종목을 선택하세요"
    stocks_disp_with_placeholder = [PLACEHOLDER] + stocks_disp

    stock_param = qp.get("stock")
    if stock_param and stock_param in code_to_disp:
        preselect_disp = code_to_disp[stock_param]
        default_idx = stocks_disp_with_placeholder.index(preselect_disp) if preselect_disp in stocks_disp_with_placeholder else 0
    else:
        default_idx = 0

    left, right = st.columns(2)

    with left:
        head_l, head_r = st.columns([10, 1])
        with head_l:
            st.markdown("**📈 종목 선택**")
        with head_r:
            with st.popover("ⓘ"):
                st.write("해당 종목들은 2024년 10월부터 수집된 한국인 매수·매도 TOP50 안에 든 종목들입니다.")
                st.write("데이터는 매일 새벽 00:10에 갱신됩니다.")

        sel_disp = st.selectbox(
            label="",
            options=stocks_disp_with_placeholder,
            index=default_idx,
            key="stock_select_chart",
        )

    with right:
        st.markdown("**⭐ 즐겨찾기**")
        favs: set = st.session_state.get("favs", set())
        fav_disp_list = sorted([code_to_disp[c] for c in favs if c in code_to_disp])
        fav_disp_list = ["(선택)"] + fav_disp_list if fav_disp_list else ["(즐겨찾기 없음)"]

        pick = st.selectbox("즐겨찾기 바로가기", fav_disp_list, key="fav_jump_chart")
        if pick and pick not in ("(선택)", "(즐겨찾기 없음)"):
            sel_disp = pick

        cur_code = disp_to_code.get(sel_disp, sel_disp) if sel_disp != PLACEHOLDER else None
        is_fav = (cur_code in favs) if cur_code else False
        star_label = "⭐ 즐겨찾기 취소" if is_fav else "☆ 즐겨찾기 추가"
        btn_disabled = (cur_code is None)

        if st.button(star_label, key="fav_toggle_btn_chart", disabled=btn_disabled):
            toggle_favorite(cur_code)

    # ✅ 여기서 st.stop() 절대 쓰지 않음.
    # 종목 미선택이면 안내만 보여주고, 차트 렌더링만 스킵.
    if sel_disp == PLACEHOLDER or not sel_disp:
        st.info("종목을 선택하거나 검색해서 시작해줘.")
    else:
        sel_stock = disp_to_code.get(sel_disp, sel_disp)

        if "range_value" not in st.session_state:
            _set_date_slider((default_start, default_end))

        Toggle = getattr(st, "toggle", st.checkbox)

        col1, col2, col3, col4, spacer, col5, col6, col7 = st.columns([1, 1, 1, 1, 3, 1, 1, 1])
        with col1:  st.button("1주 (5일)",     key="btn_5",   on_click=compute_last_n_trading_days, args=(sel_stock, 5))
        with col2:  st.button("1개월 (20일)",  key="btn_20",  on_click=compute_last_n_trading_days, args=(sel_stock, 20))
        with col3:  st.button("3개월 (60일)",  key="btn_60",  on_click=compute_last_n_trading_days, args=(sel_stock, 60))
        with col4:  st.button("6개월 (120일)", key="btn_120", on_click=compute_last_n_trading_days, args=(sel_stock, 120))

        with col5:  st.write("**지표**")
        with col6:  ma5_on  = Toggle("MA5",  value=False, key="tg_ma5_chart")
        with col7:  ma10_on = Toggle("MA10", value=True,  key="tg_ma10_chart")
        with spacer: ma20_on = Toggle("MA20", value=True,  key="tg_ma20_chart")

        date_range = st.slider(
            "기간 선택", min_value=min_date, max_value=max_date,
            value=st.session_state["range_value"], key="range_slider", format="YYYY-MM-DD",
        )

        dcount = int(
            df.loc[
                (df["종목명"] == sel_stock)
                & (df["날짜"].dt.date >= date_range[0])
                & (df["날짜"].dt.date <= date_range[1]),
                "날짜"
            ].dt.date.nunique()
        )
        st.markdown(
            f"<div style='text-align:center; color:#666; margin:-6px 0 8px;'>"
            f"<strong>기간 합계</strong> ({date_range[0]} ~ {date_range[1]}, {dcount}일)"
            f"</div>",
            unsafe_allow_html=True
        )

        mask = (
            (df["종목명"] == sel_stock)
            & (df["날짜"].dt.date >= date_range[0])
            & (df["날짜"].dt.date <= date_range[1])
        )
        data = df.loc[mask].copy().sort_values("날짜")

        if data.empty:
            st.warning("선택한 종목/기간의 데이터가 없습니다.")
        else:
            mid_l, mid_c, mid_r = st.columns([1, 2, 1])
            with mid_c:
                logo_path = find_logo_path(sel_stock)
                render_title_line(logo_path, sel_disp, size=86, align="center")

            total_buy  = float(data["매수"].sum())
            total_sell = float(data["매도"].sum())
            total_net  = float(data["순매수"].sum())
            ratio = (total_buy / total_sell) if total_sell != 0 else None

            st.markdown("""
                <style>
                .kpi-wrap{display:flex; gap:2rem; justify-content:space-between; margin:6px 0 10px 0;}
                .kpi{flex:1; text-align:center;}
                .kpi-label{font-weight:700; font-size:0.95rem; margin-bottom:0.15rem;}
                .kpi-buy{color:#d62728;} .kpi-sell{color:#1f77b4;}
                .kpi-value{font-weight:600; font-size:1.6rem; line-height:1.1; margin:0; padding:0;}
                </style>
            """, unsafe_allow_html=True)

            st.markdown(f"""
            <div class='kpi-wrap'>
              <div class='kpi'><div class='kpi-label kpi-buy'>총 매수(USD)</div><div class='kpi-value'>{fmt_usd(total_buy)}</div></div>
              <div class='kpi'><div class='kpi-label kpi-sell'>총 매도(USD)</div><div class='kpi-value'>{fmt_usd(total_sell)}</div></div>
              <div class='kpi'><div class='kpi-label'>총 순매수(USD)</div><div class='kpi-value'>{fmt_usd(total_net)}</div></div>
              <div class='kpi'><div class='kpi-label'>⚖️ 매수:매도 비율</div><div class='kpi-value'>{(f"{ratio:.2f} : 1" if ratio else "-")}</div></div>
            </div>
            """, unsafe_allow_html=True)

            data["날짜_str"] = data["날짜"].dt.strftime("%Y-%m-%d")
            x_enc = alt.X("날짜_str:N", title="거래일", sort=None)

            bar = (
                alt.Chart(data)
                .mark_bar()
                .encode(
                    x=x_enc,
                    y=alt.Y("순매수:Q", title="순매수, MA"),
                    color=alt.condition("datum.순매수 >= 0", alt.value("#d62728"), alt.value("#1f77b4")),
                    tooltip=[
                        alt.Tooltip("날짜:T", title="날짜"),
                        alt.Tooltip("표시명:N", title="종목"),
                        alt.Tooltip("순매수:Q", title="순매수", format=",.0f"),
                    ],
                )
            )

            ma_cols = []
            if ma5_on:  ma_cols.append("MA5")
            if ma10_on: ma_cols.append("MA10")
            if ma20_on: ma_cols.append("MA20")

            layers = [bar]
            if ma_cols:
                lines_df = data.melt(
                    id_vars=["날짜", "날짜_str"],
                    value_vars=ma_cols,
                    var_name="지표",
                    value_name="값",
                )
                line = (
                    alt.Chart(lines_df)
                    .mark_line(strokeWidth=2)
                    .encode(
                        x=x_enc,
                        y=alt.Y("값:Q"),
                        color=alt.Color("지표:N", title=None, legend=alt.Legend(orient="top-right")),
                        tooltip=[
                            alt.Tooltip("날짜:T", title="날짜"),
                            alt.Tooltip("지표:N"),
                            alt.Tooltip("값:Q", title="값", format=",.0f"),
                        ]
                    )
                )
                layers.append(line)

            chart = alt.layer(*layers).resolve_scale(y="shared").properties(height=520)
            st.altair_chart(chart, use_container_width=True)

# ───────────────────────────
# 2) 🏆 인기 종목 TOP50
# ───────────────────────────
with t_top:
    st.markdown("### 🏆 인기 종목 TOP50 (등장일수 기준)")
    df_period = df[(df["날짜"].dt.date >= default_start) & (df["날짜"].dt.date <= default_end)]
    if df_period.empty:
        st.warning("선택 기간 데이터가 없습니다.")
    else:
        n_days = df_period["날짜"].dt.date.nunique()
        hits = (
            df_period.dropna(subset=["표시명"])
            .groupby(["표시명", "종목명"])["날짜"].nunique()
            .reset_index(name="등장일수")
            .sort_values("등장일수", ascending=False)
            .head(50)
        )
        hits["커버리지(%)"] = (hits["등장일수"] / n_days * 100).round(1)
        hits["link"] = hits["종목명"].apply(lambda s: f"?tab=chart&stock={quote_plus(str(s))}")
        chart_top = (
            alt.Chart(hits)
            .mark_bar()
            .encode(
                x=alt.X("등장일수:Q", title="등장 일수"),
                y=alt.Y("표시명:N", sort="-x",
                        axis=alt.Axis(labelOverlap=False, labelLimit=2000, labelFontSize=11)),
                tooltip=["표시명:N", "등장일수:Q", "커버리지(%):Q"],
            )
            .properties(height=1200)
        )
        st.altair_chart(chart_top, use_container_width=True)

# ───────────────────────────
# 3) 📊 순매수/순매도 순위
# ───────────────────────────
with t_rank:
    st.markdown("### 📊 순매수·순매도 상위 종목")

    col0, col1, col2, col3, col4, col5, _ = st.columns([1, 1, 1, 1, 1, 1, 4.5])
    with col0: period_1  = st.button("1일",  key="btn_r_1")
    with col1: period_5  = st.button("5일",  key="btn_r_5")
    with col2: period_10 = st.button("10일", key="btn_r_10")
    with col3: period_20 = st.button("20일", key="btn_r_20")
    with col4: period_40 = st.button("40일", key="btn_r_40")
    with col5: period_60 = st.button("60일", key="btn_r_60")

    trading_days = sorted(df["날짜"].dt.date.unique().tolist())
    if not trading_days:
        st.warning("데이터가 없습니다.")
    else:
        t_min, t_max = trading_days[0], trading_days[-1]

        def set_rank_range_last_n(n: int):
            start = trading_days[-n] if len(trading_days) >= n else t_min
            _set_rank_slider((start, t_max))

        if "rank_range" not in st.session_state:
            set_rank_range_last_n(20)

        if period_1:  set_rank_range_last_n(1)
        if period_5:  set_rank_range_last_n(5)
        if period_10: set_rank_range_last_n(10)
        if period_20: set_rank_range_last_n(20)
        if period_40: set_rank_range_last_n(40)
        if period_60: set_rank_range_last_n(60)

        rank_range = st.slider(
            "기간 선택",
            min_value=t_min,
            max_value=t_max,
            value=st.session_state["rank_range"],
            key="rank_range_slider",
            format="YYYY-MM-DD",
        )
        st.session_state["rank_range"] = rank_range

        mode = st.radio("보기", ["순매수 상위", "순매도 상위"], horizontal=True, key="rank_mode")

        start, end = rank_range
        period_df = df[(df["날짜"].dt.date >= start) & (df["날짜"].dt.date <= end)]

        agg = (
            period_df
            .groupby(["표시명", "종목명"], as_index=False)[["매수", "매도", "순매수"]]
            .sum()
            .rename(columns={"매수":"매수합계","매도":"매도합계"})
        )

        if mode == "순매도 상위":
            agg["순매도합계"] = -agg["순매수"]
            plot_df = agg[agg["순매도합계"] > 0].sort_values("순매도합계", ascending=False).head(50)
            x_field = "순매도합계:Q"
            x_title = "순매도 합계 (USD)"
            tooltip_fields = [
                "표시명:N",
                alt.Tooltip("순매도합계:Q", title="순매도", format=",.0f"),
                alt.Tooltip("매수합계:Q",   title="매수",   format=",.0f"),
                alt.Tooltip("매도합계:Q",   title="매도",   format=",.0f"),
            ]
        else:
            plot_df = agg[agg["순매수"] > 0].sort_values("순매수", ascending=False).head(50)
            x_field = "순매수:Q"
            x_title = "순매수 합계 (USD)"
            tooltip_fields = [
                "표시명:N",
                alt.Tooltip("순매수:Q",   title="순매수", format=",.0f"),
                alt.Tooltip("매수합계:Q", title="매수",   format=",.0f"),
                alt.Tooltip("매도합계:Q", title="매도",   format=",.0f"),
            ]

        plot_df["link"] = plot_df["종목명"].apply(lambda s: f"?tab=chart&stock={quote_plus(str(s))}")

        chart_rank = (
            alt.Chart(plot_df)
            .mark_bar()
            .encode(
                x=alt.X(x_field, title=x_title, scale=alt.Scale(domainMin=0, nice=True)),
                y=alt.Y("표시명:N", sort="-x", title=None,
                        axis=alt.Axis(labelLimit=2500, labelFontSize=11)),
                tooltip=tooltip_fields,
            )
            .properties(height=1200)
        )
        st.altair_chart(chart_rank, use_container_width=True)

# ───────────────────────────
# 4) 🧪 조건 필터
# ───────────────────────────
with t_filter:
    st.markdown("### 🧪 조건 필터 (교집합 AND, 최근 20거래일)")

    Toggle = getattr(st, "toggle", st.checkbox)
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        use_ratio = Toggle("최근 20일 매수/매도 ≤ 0.9", value=True,
                           help="최근 20 거래일간 BUY/SELL 합계 비율", key="f_use_ratio")
    with c2:
        use_ma5  = Toggle("MA5 ≤ 0",  value=True, key="f_use_ma5")
    with c3:
        use_ma10 = Toggle("MA10 ≤ 0", value=False, key="f_use_ma10")
    with c4:
        use_ma20 = Toggle("MA20 ≤ 0", value=False, key="f_use_ma20")

    trade_days = sorted(df["날짜"].dt.date.unique())
    if not trade_days:
        st.warning("데이터가 없습니다.")
    else:
        last_day = trade_days[-1]
        start_idx = max(0, len(trade_days) - 20)
        first_day = trade_days[start_idx]

        period_df = df[(df["날짜"].dt.date >= first_day) & (df["날짜"].dt.date <= last_day)].copy()

        agg = (
            period_df.groupby(["종목명", "표시명"], as_index=False)[["매수", "매도"]].sum()
            .rename(columns={"매수": "최근20일_매수합", "매도": "최근20일_매도합"})
        )
        agg["비율(BUY/SELL)"] = agg.apply(
            lambda r: (r["최근20일_매수합"] / r["최근20일_매도합"]) if r["최근20일_매도합"] not in (0, None) else float("inf"),
            axis=1
        )

        last_ma = (
            period_df
            .sort_values("날짜")
            .groupby(["종목명", "표시명"], as_index=False)[["MA5", "MA10", "MA20"]]
            .last()
        )

        res = pd.merge(agg, last_ma, on=["종목명", "표시명"], how="left")

        cond = pd.Series([True] * len(res))
        if use_ratio:
            cond &= (res["비율(BUY/SELL)"] <= 0.9)
        if use_ma5:
            cond &= (res["MA5"] <= 0)
        if use_ma10:
            cond &= (res["MA10"] <= 0)
        if use_ma20:
            cond &= (res["MA20"] <= 0)

        filtered = res.loc[cond].copy()
        filtered = filtered.sort_values(
            by=["비율(BUY/SELL)", "최근20일_매수합"],
            ascending=[True, False]
        )

        for c in ["최근20일_매수합", "최근20일_매도합", "MA5", "MA10", "MA20"]:
            if c in filtered.columns:
                filtered[c] = filtered[c].round(0)

        st.caption(f"기간: {first_day} ~ {last_day} (총 {len(trade_days[start_idx:])} 거래일)")
        st.write(f"**적용 조건 수:** {sum([use_ratio, use_ma5, use_ma10, use_ma20])}개 | **결과 종목:** {len(filtered)}개")

        show_cols = ["표시명", "종목명", "최근20일_매수합", "최근20일_매도합", "비율(BUY/SELL)", "MA5", "MA10", "MA20"]
        st.dataframe(filtered[show_cols], use_container_width=True, hide_index=True)

        names = ["(선택)"] + filtered["표시명"].tolist()
        pick = st.selectbox("결과에서 선택 → 차트 보기", names, index=0, key="filter_pick")
        if pick and pick != "(선택)":
            code = filtered.loc[filtered["표시명"] == pick, "종목명"].iloc[0]
            st.markdown(f"[📈 차트로 이동]({f'?tab=chart&stock={quote_plus(str(code))}'})")

# ───────────────────────────
# 5) 📘 소개/가이드 (가로 카드 3개)
# ───────────────────────────
with t_guide:
    st.markdown("### 📘 소개 / 가이드")

    st.markdown("""
    <style>
      .guide-card {
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 14px;
        padding: 16px 16px 14px 16px;
        background: rgba(255,255,255,0.03);
        height: 100%;
        font-family: """ + FONT_STACK + """;
      }
      .guide-title { font-size: 18px; font-weight: 800; margin-bottom: 10px; }
      .guide-body  { font-size: 14px; line-height: 1.55; color: rgba(255,255,255,0.85); }
      .muted { color: rgba(255,255,255,0.65); }
    </style>
    """, unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)

    with c1:
        st.markdown("""
        <div class="guide-card">
          <div class="guide-title">📊 이 대시보드는 무엇인가요?</div>
          <div class="guide-body">
            한국 개인 투자자들의 <b>미국 주식 순매수·순매도 흐름</b>을 시각화한 데이터 도구입니다.<br/>
            특정 종목이 <b>언제, 얼마나, 어떤 방향으로</b> 매수·매도되는지 한눈에 확인할 수 있습니다.
          </div>
        </div>
        """, unsafe_allow_html=True)

    with c2:
        st.markdown("""
        <div class="guide-card">
          <div class="guide-title">📈 왜 만들었나요?</div>
          <div class="guide-body">
            주가는 항상 펀더멘털만으로 움직이지 않습니다.<br/>
            관심, 유행, 공포와 기대 같은 <b>집단 심리</b> 역시 가격에 강하게 반영됩니다.<br/><br/>
            이 도구는 <b>주가 흐름과 투자자 심리(유행)의 상관관계</b>를 관찰하기 위해 만들어졌습니다.
          </div>
        </div>
        """, unsafe_allow_html=True)

    with c3:
        st.markdown("""
        <div class="guide-card">
          <div class="guide-title">🗂 어떤 데이터를 사용하나요?</div>
          <div class="guide-body">
            2024년 10월 이후<br/>
            <b>한국인 순매수·순매도 TOP50</b>에 한 번이라도 포함된 종목들만을 대상으로 합니다.<br/><br/>
            데이터는 <b>매일 갱신</b>되며,<br/>
            원본 출처는 <b>SEIBRO</b>입니다.
          </div>
        </div>
        """, unsafe_allow_html=True)
