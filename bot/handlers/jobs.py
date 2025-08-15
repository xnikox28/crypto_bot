from __future__ import annotations
import asyncio
import io
import logging
import time
from typing import Optional, Dict

import numpy as np
import pandas as pd
from telegram.ext import ContextTypes, Application

from ..config import Config
from ..db import repo
from ..db.models import ChatState

from ..services.market import okx_klines, cg_prices_df
from ..services.indicators import ema, rsi, macd
from ..services.levels import get_levels
from ..services.plotting import plot_chart
from ..services.formatting import fmt_price

log = logging.getLogger("jobs")

async def send_text(ctx: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str):
    await ctx.bot.send_message(chat_id=chat_id, text=text)

async def send_photo(ctx: ContextTypes.DEFAULT_TYPE, chat_id: int, buf: io.BytesIO, caption: str):
    await ctx.bot.send_photo(chat_id=chat_id, photo=buf, caption=caption)

def modo_params(modo: str) -> Dict[str, float]:
    if modo == "agresivo":
        return {"pre_break_buffer": 0.006, "rsi_buy": 35, "rsi_sell": 65}
    if modo == "conservador":
        return {"pre_break_buffer": 0.003, "rsi_buy": 30, "rsi_sell": 70}
    return {"pre_break_buffer": 0.004, "rsi_buy": 33, "rsi_sell": 67}

async def get_4h_context(coin_id: str, symbol_okx: str) -> Optional[Dict]:
    df_15 = await okx_klines(symbol_okx, "15m", 400)
    if df_15 is None:
        df_1h = await cg_prices_df(coin_id, days=8)
        if df_1h is None:
            return None
        df_4h = df_1h.set_index("time").resample("4h").last().dropna().reset_index()
    else:
        df_4h = (
            df_15.set_index("time")[["open","high","low","close"]]
            .resample("4h").agg({"open":"first","high":"max","low":"min","close":"last"})
            .dropna().reset_index()
        )
    close = df_4h["close"]
    rsi4s = rsi(close,14)
    e20s = ema(close,20); e50s=ema(close,50); e200s=ema(close,200)
    rsi_last = float(rsi4s.iloc[-1])
    e20 = float(e20s.iloc[-1]); e50=float(e50s.iloc[-1]); e200=float(e200s.iloc[-1])
    price_last = float(close.iloc[-1])
    return {
        "df": df_4h,
        "rsi": rsi_last,
        "ema20": e20, "ema50": e50, "ema200": e200,
        "trend_up": (rsi_last > 50) and (price_last > e50),
        "trend_down": (rsi_last < 50) and (price_last < e50),
    }

async def get_15m_oper(coin_id: str, symbol_okx: str) -> Optional[Dict]:
    df_15 = await okx_klines(symbol_okx, "15m", 400)
    if df_15 is None:
        df_1h = await cg_prices_df(coin_id, days=3)
        if df_1h is None: return None
        df_15 = (
            df_1h.set_index("time").resample("15min").pad().dropna().reset_index().rename(columns={"close":"close"})
        )
        df_15["open"]=df_15["close"]; df_15["high"]=df_15["close"]; df_15["low"]=df_15["close"]
    close = df_15["close"]
    m,s,h = macd(close)
    return {
        "df": df_15,
        "price": float(close.iloc[-1]),
        "rsi": float(rsi(close,14).iloc[-1]),
        "ema20": float(ema(close,20).iloc[-1]),
        "ema50": float(ema(close,50).iloc[-1]),
        "ema200": float(ema(close,200).iloc[-1]),
        "macd_up": bool(m.iloc[-1] > s.iloc[-1]),
    }

async def get_5m_execution(coin_id: str, symbol_okx: str) -> Optional[Dict]:
    df_5 = await okx_klines(symbol_okx, "5m", 300)
    if df_5 is None:
        df_15 = await okx_klines(symbol_okx, "15m", 200)
        if df_15 is None: return None
        df_5 = (
            df_15.set_index("time")["close"].resample("5min").pad().dropna().reset_index().rename(columns={"close":"close"})
        )
    close = df_5["close"] if "close" in df_5 else df_5.iloc[:, -1]
    m,s,h = macd(close)
    return {
        "df": df_5 if isinstance(df_5, pd.DataFrame) else df_5.to_frame(),
        "rsi": float(rsi(close,14).iloc[-1]),
        "macd_up": bool(m.iloc[-1] > s.iloc[-1]),
        "price": float(close.iloc[-1]),
    }

def ensure_chat_job(app: Application, chat_id: int, poll_sec: int):
    name = f"hb:{chat_id}"
    for job in app.job_queue.jobs():
        if job.name == name:
            return
    app.job_queue.run_repeating(
        heartbeat_job, interval=poll_sec, first=3, name=name,
        chat_id=chat_id, data={"chat_id": chat_id},
    )

async def heartbeat_job(ctx: ContextTypes.DEFAULT_TYPE):
    app = ctx.application
    cfg: Config = app.bot_data["config"]
    chat_id = ctx.job.chat_id if getattr(ctx, "job", None) else None
    if chat_id is None and getattr(ctx, "job", None) and ctx.job.data:
        chat_id = ctx.job.data.get("chat_id")
    if chat_id is None:
        return

    st = await repo.get_chat(cfg.db_path, chat_id)
    if not st:
        st = ChatState(chat_id=chat_id)
        await repo.upsert_chat(cfg.db_path, st)

    if not bool(st.alerts_on):
        return

    ctx4, op15, ex5, levels = await asyncio.gather(
        get_4h_context(st.coin_id, st.symbol_okx),
        get_15m_oper(st.coin_id, st.symbol_okx),
        get_5m_execution(st.coin_id, st.symbol_okx),
        get_levels(st.coin_id, st.symbol_okx),
    )
    if None in (ctx4, op15, ex5):
        log.warning("[WARN] datos insuficientes en heartbeat")
        return

    # Precision desde BD (NO desde bot_data)
    precision_on: bool = bool(getattr(st, "precision_on", 0))

    # ===== Indicadores (15m) =====
    df15 = op15["df"]
    close15 = df15["close"]
    idx_c = -2 if len(close15) >= 2 and precision_on else -1

    price15_c = float(close15.iloc[idx_c])
    rsi15_series = rsi(close15, 14)
    rsi15_c = float(rsi15_series.iloc[idx_c])
    rsi15_prev = float(rsi15_series.iloc[idx_c - 1]) if len(rsi15_series) >= 2 else rsi15_c
    m15, s15, h15 = macd(close15)
    macd15_up_c = bool(m15.iloc[idx_c] > s15.iloc[idx_c])
    hist15_grows = bool(h15.iloc[idx_c] > h15.iloc[idx_c - 1]) if len(h15) >= 2 else False
    ema20_series = ema(close15, 20); ema50_series = ema(close15, 50); ema200_series = ema(close15, 200)
    ema20_c = float(ema20_series.iloc[idx_c]); ema50_c = float(ema50_series.iloc[idx_c]); ema200_c = float(ema200_series.iloc[idx_c])

    # 5m
    df5 = ex5["df"]
    close5 = df5["close"] if "close" in df5 else df5.iloc[:, -1]
    idx5_c = -2 if len(close5) >= 2 and precision_on else -1
    m5, s5, h5 = macd(close5)
    macd5_up_c = bool(m5.iloc[idx5_c] > s5.iloc[idx5_c])
    rsi5_series = rsi(close5, 14); rsi5_c = float(rsi5_series.iloc[idx5_c])

    # 4H filtro extra si precisión
    rsi4 = float(ctx4["rsi"])
    e4_20 = float(ctx4.get("ema20", 0.0)); e4_50 = float(ctx4.get("ema50", 0.0)); e4_200 = float(ctx4.get("ema200", 0.0))
    trend_up_strict = (rsi4 > 52.0) and (e4_20 > e4_50 > e4_200)

    # Fibo 0.618
    f618 = levels.get("F618") if levels else None
    fib_ok = True
    if precision_on and f618:
        low15_c = float(df15["low"].iloc[idx_c]) if "low" in df15.columns else price15_c
        prev_close = float(close15.iloc[idx_c - 1]) if len(close15) >= 2 else price15_c
        breakout = (prev_close < f618) and (price15_c >= f618 * (1 + 0.0005))
        retest   = (price15_c >= f618) and (low15_c <= f618 * (1 + 0.0010))
        fib_ok = bool(breakout or retest)

    # Cooldown por velas 15m
    rt = app.bot_data.setdefault("runtime", {})
    last_entry_bar = rt.get(("last_entry_bar15", chat_id))
    enough_cooldown = True
    if precision_on and last_entry_bar is not None:
        try:
            idx_last = df15.index[df15["time"] == last_entry_bar][0]
            idx_now  = df15.index[-1 if idx_c == -1 else -2]
            enough_cooldown = (idx_now - idx_last) >= 6  # ~90 min
        except Exception:
            enough_cooldown = True

    # ===== Entrada =====
    mp = modo_params(st.modo)
    if precision_on:
        thresh = max(40.0, mp["rsi_buy"])
        rsi_cross_up = (rsi15_prev < thresh) and (rsi15_c >= (thresh + 0.8))
        entry_signal = (
            trend_up_strict
            and (price15_c > ema20_c) and (ema20_c > ema50_c)
            and macd15_up_c and hist15_grows
            and rsi15_c > 45.0 and rsi_cross_up
            and macd5_up_c and (rsi5_c > 50.0)
            and fib_ok and enough_cooldown
        )
    else:
        trend_up = bool(ctx4["trend_up"])
        rsi15_now = float(op15["rsi"]); macd15u = bool(op15["macd_up"])
        rsi5_now = float(ex5["rsi"]); macd5u = bool(ex5["macd_up"])
        ema20_val = float(op15["ema20"]); price_now = float(op15["price"])
        entry_signal = trend_up and (rsi15_now < max(40, mp["rsi_buy"])) and macd15u and (price_now > ema20_val) and macd5u and (rsi5_now > 45)

    if st.position_entry is None and entry_signal:
        st.position_entry = price15_c if precision_on else float(op15["price"])
        await repo.update_fields(cfg.db_path, chat_id, position_entry=st.position_entry)
        try:
            rt[("last_entry_bar15", chat_id)] = df15["time"].iloc[idx_c]
        except Exception:
            pass
        await send_text(
            ctx, chat_id,
            (f"🟢 ENTRADA (virtual) {st.coin_id.upper()} — TF 4H/15M/5M\n"
             f"Precio: ${fmt_price(st.symbol_okx, st.position_entry)}\n"
             f"Confluencias: "
             f"{'4H EMA20>50>200 · ' if precision_on else ''}"
             f"15M MACD↑{' hist↑ ·' if precision_on else ' ·'} RSI ok · 5M MACD↑ "
             f"{'· F618 OK' if precision_on else ''}")
        )

    # ===== Gestión TP/SL/Trailing =====
    peak_map = rt.setdefault(("peak",), {})
    peak = peak_map.get(chat_id)

    if st.position_entry is not None:
        price_now = price15_c if precision_on else float(op15["price"])
        pe = st.position_entry
        if peak is None or price_now > peak:
            peak = price_now; peak_map[chat_id] = peak

        gain = (price_now - pe) / max(pe, 1e-12)
        tp = st.tp_pct / 100.0; sl = st.sl_pct / 100.0

        if gain >= tp:
            await send_text(ctx, chat_id, f"🏆 TP +{gain*100:.2f}% — VENDER {st.coin_id.upper()} ahora. Precio ${fmt_price(st.symbol_okx, price_now)}")
            st.position_entry = None; peak_map.pop(chat_id, None)
            await repo.update_fields(cfg.db_path, chat_id, position_entry=None)
        elif gain <= -sl:
            await send_text(ctx, chat_id, f"🔻 SL {gain*100:.2f}% — SALIR YA de {st.coin_id.upper()}. Precio ${fmt_price(st.symbol_okx, price_now)}")
            st.position_entry = None; peak_map.pop(chat_id, None)
            await repo.update_fields(cfg.db_path, chat_id, position_entry=None)
        else:
            if gain >= 0.01 and peak:
                dd = (peak - price_now) / peak
                if dd >= 0.008:
                    await send_text(ctx, chat_id, f"🛡️ Trailing activado (drawdown {dd*100:.2f}%) — salir de {st.coin_id.upper()}. Precio ${fmt_price(st.symbol_okx, price_now)}")
                    st.position_entry = None; peak_map.pop(chat_id, None)
                    await repo.update_fields(cfg.db_path, chat_id, position_entry=None)

            weak_exit = (not macd5_up_c) and (price15_c < ema20_c) if precision_on else (not bool(ex5["macd_up"])) and (float(op15["price"]) < float(op15["ema20"]))
            if weak_exit and gain > 0:
                await send_text(ctx, chat_id, f"⚠️ Debilidad intradía — MACD 5m↓ y precio < EMA20 15m. Considera salir (+{gain*100:.2f}%).")

    # ===== Peligro (S1/S2) =====
    danger_condition = False
    if levels:
        pre_buf = modo_params(st.modo)["pre_break_buffer"]
        price_chk = price15_c if precision_on else float(op15["price"])
        def near(level: float) -> bool:
            return abs(price_chk - level) / max(level, 1e-9) <= pre_buf and price_chk <= level * (1 + pre_buf)
        rsi15_now = rsi15_c if precision_on else float(op15["rsi"])
        macd15_now_up = macd15_up_c if precision_on else bool(op15["macd_up"])
        macd5_now_up  = macd5_up_c if precision_on else bool(ex5["macd_up"])
        ema20_now = ema20_c if precision_on else float(op15["ema20"])
        bearish_confluence = (rsi15_now < 45) and (not macd15_now_up) and (price_chk < ema20_now) and (not macd5_now_up)
        near_s = any((k in levels) and np.isfinite(levels[k]) and near(levels[k]) for k in ("S1","S2"))
        danger_condition = bearish_confluence and near_s
        if danger_condition:
            try:
                tgt = min(("S1","S2"), key=lambda k: abs(price_chk - levels[k]) if k in levels and np.isfinite(levels[k]) else float("inf"))
            except Exception:
                tgt = "S1"
            await send_text(ctx, chat_id, f"⚠️ PELIGRO: {st.coin_id.upper()} muy cerca de {tgt} ${fmt_price(st.symbol_okx, levels.get(tgt))} (15M bajista y 5M sin confirmación). ➡️ SELL NOW.")

    # ===== Imagen con cooldown =====
    ps = app.bot_data.setdefault("runtime", {}).setdefault(("plot_state", chat_id), {"last_plot_ts": 0})
    now_ts = time.time()
    ENTRY_PLOT_COOLDOWN_SEC, DANGER_PLOT_COOLDOWN_SEC = 300, 1800

    def _send_plot_ok(cooldown: int) -> bool:
        return (now_ts - ps["last_plot_ts"]) > cooldown

    if st.position_entry is not None and _send_plot_ok(ENTRY_PLOT_COOLDOWN_SEC):
        try:
            df = op15["df"]
            ema20s = ema(df["close"],20); ema50s=ema(df["close"],50); ema200s=ema(df["close"],200)
            buf = await asyncio.to_thread(
                plot_chart, df, (levels or {}), ema20s, ema50s, ema200s,
                title=f"{st.coin_id.upper()} — 15M con Niveles & EMAs",
                inst_id=st.symbol_okx,
            )
            caption = (f"Precio {fmt_price(st.symbol_okx, float(op15['price']))} | RSI(4H/15M/5M): "
                       f"{float(ctx4['rsi']):.1f}/{float(op15['rsi']):.1f}/{float(ex5['rsi']):.1f}")
            await send_photo(ctx, chat_id, buf, caption); ps["last_plot_ts"] = now_ts
        except Exception as e:
            log.warning("plot send error (entry): %s", e)
    elif danger_condition and _send_plot_ok(DANGER_PLOT_COOLDOWN_SEC):
        try:
            df = op15["df"]
            ema20s = ema(df["close"],20); ema50s=ema(df["close"],50); ema200s=ema(df["close"],200)
            buf = await asyncio.to_thread(
                plot_chart, df, (levels or {}), ema20s, ema50s, ema200s,
                title=f"{st.coin_id.upper()} — 15M con Niveles & EMAs",
                inst_id=st.symbol_okx,
            )
            caption = (f"Precio {fmt_price(st.symbol_okx, float(op15['price']))} | RSI(4H/15M/5M): "
                       f"{float(ctx4['rsi']):.1f}/{float(op15['rsi']):.1f}/{float(ex5['rsi']):.1f}")
            await send_photo(ctx, chat_id, buf, caption); ps["last_plot_ts"] = now_ts
        except Exception as e:
            log.warning("plot send error (danger): %s", e)
