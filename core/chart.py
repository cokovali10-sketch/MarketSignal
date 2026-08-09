"""График истории цены картинкой (matplotlib)."""

import io

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import MaxNLocator  # noqa: E402


def render_chart(points) -> bytes:
    """Отрисовать историю цены. points — список PricePoint (по возрастанию времени).

    Возвращает PNG-байты.
    """
    if not points:
        raise ValueError("no points")

    times = [p.ts for p in points]
    prices = [p.price if p.price is not None else 0 for p in points]

    fig, ax = plt.subplots(figsize=(8, 4), dpi=110)
    ax.plot(times, prices, marker="o", color="#2f80ed", linewidth=2.2, markersize=4)

    min_p, max_p = min(prices), max(prices)
    pad = max((max_p - min_p) * 0.1, 1.0)
    ax.set_ylim(max(0, min_p - pad), max_p + pad)
    ax.yaxis.set_major_locator(MaxNLocator(nbins=6))

    for x, y in zip(times, prices, strict=False):
        ax.annotate(
            f"{y:,.0f}".replace(",", " "),
            (x, y),
            textcoords="offset points",
            xytext=(0, 8),
            ha="center",
            fontsize=8,
            color="#333",
        )

    ax.set_title("История цены", fontsize=13, pad=12)
    ax.set_ylabel("Цена, ₽")
    ax.grid(axis="y", alpha=0.3)
    ax.set_axisbelow(True)
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return buf.read()
