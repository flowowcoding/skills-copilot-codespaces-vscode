import marimo

__generated_with = "0.25.1"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    import altair as alt
    import pandas as pd

    from backtest import CONTROL, LANDLORDS, Config, equity_curves, fmt, run
    return CONTROL, Config, LANDLORDS, alt, equity_curves, fmt, mo, pd, run


@app.cell
def _(mo):
    mo.md(r"""
    # Cushing tank signal: does the head start matter?

    Rule from the video: when Cushing stocks rise that week, own the tank "landlords";
    when they fall, sell. The same rule runs on three information schedules:

    - **oracle**: you know the change *during* the week it happens (look-ahead, upper bound)
    - **satellite**: you know it at the Friday the week ends, days before EIA publishes
    - **public**: you trade at the close on EIA release day, with the number everyone has

    If **public** does as well as **satellite**, the satellite adds nothing.
    """)
    return


@app.cell
def _(CONTROL, LANDLORDS, mo):
    ticker = mo.ui.dropdown(LANDLORDS + CONTROL, value="PAA", label="Ticker")
    cost = mo.ui.slider(0, 30, step=1, value=5, label="Cost (bps per side)")
    long_short = mo.ui.checkbox(label="Short when draining (else flat)")
    mo.hstack([ticker, cost, long_short], justify="start", gap=2)
    return cost, long_short, ticker


@app.cell
def _(Config, cost, long_short):
    cfg = Config(cost_bps=cost.value, long_short=long_short.value, n_random=500)
    return (cfg,)


@app.cell
def _(alt, cfg, equity_curves, pd, ticker):
    curves = equity_curves(cfg, ticker.value)
    order = ["buy&hold", "oracle", "satellite", "public"]
    # Default validated categorical slots 1-4, fixed per series.
    colors = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
    long = curves.reset_index(names="date").melt("date", var_name="strategy", value_name="growth")
    weekly = long[long["date"].dt.dayofweek == 4]
    color = alt.Color("strategy:N", scale=alt.Scale(domain=order, range=colors),
                      sort=order, legend=alt.Legend(orient="top", title=None))
    hover = alt.selection_point(fields=["date"], nearest=True, on="pointerover", empty=False)
    base = alt.Chart(weekly).encode(
        x=alt.X("date:T", title=None),
        y=alt.Y("growth:Q", scale=alt.Scale(type="log"), title="Growth of $1 (log)"),
    )
    lines = base.mark_line(strokeWidth=2).encode(color=color)
    rule = alt.Chart(weekly).mark_rule(color="#8a8984").encode(
        x="date:T",
        opacity=alt.condition(hover, alt.value(1), alt.value(0)),
        tooltip=[alt.Tooltip("date:T")] + [
            alt.Tooltip(f"{s}:Q", format=".2f") for s in order
        ],
    ).transform_pivot("strategy", value="growth", groupby=["date"]).add_params(hover)
    points = base.mark_point(size=64, filled=True).encode(
        color=color, opacity=alt.condition(hover, alt.value(1), alt.value(0)))
    chart = (lines + rule + points).properties(
        width="container", height=360, title=f"{ticker.value}: growth of $1, weekly",
    ).configure_view(stroke=None).configure_axis(gridColor="#e8e7e3", domainColor="#c3c2b7")
    chart
    return


@app.cell
def _(cfg, fmt, mo, run):
    table, corr = run(cfg)
    mo.vstack([
        mo.md("## All tickers\n`beats_random` = share of 500 coin-flip strategies on the same schedule and cost that this one beats."),
        mo.plain_text(fmt(table)),
        mo.md("## How many independent tests are there?\nCorrelation of daily strategy returns, satellite schedule."),
        corr.round(2),
    ])
    return


if __name__ == "__main__":
    app.run()
