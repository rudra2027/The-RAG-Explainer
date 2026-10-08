"""
make_lottie.py - builds the small Lottie animations used by the UI (static/lottie/*.json).

WHY generate them: a Lottie file is just JSON describing shapes + keyframes.
Writing them from code keeps the repo self-contained (no account or download
needed) and shows students there is no magic inside a Lottie file.

The UI plays them with LottieFiles' official player (<dotlottie-wc>). To use any
animation from lottiefiles.com instead, replace the `src` in static/index.html.

Run:  python scripts/make_lottie.py
"""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "static" / "lottie"
FRAMES = 90   # 3 seconds at 30 fps
SIZE = 200

# Brand colours as Lottie RGBA (0..1)
INDIGO = [0.31, 0.27, 0.90, 1]
VIOLET = [0.49, 0.23, 0.93, 1]
CYAN = [0.02, 0.71, 0.83, 1]
EMERALD = [0.06, 0.73, 0.51, 1]
ROSE = [0.96, 0.25, 0.37, 1]
AMBER = [0.96, 0.62, 0.04, 1]


# ---- tiny helpers -------------------------------------------------------------
def static(value):
    return {"a": 0, "k": value}


def animated(*keys):
    """keys = (frame, value), ... -> eased keyframes (value may be a number or a list)."""
    frames = []
    for i, (t, v) in enumerate(keys):
        v = v if isinstance(v, list) else [v]
        kf = {"t": t, "s": v}
        if i < len(keys) - 1:  # every keyframe except the last says how to ease to the next one
            kf["i"] = {"x": [0.4] * len(v), "y": [1] * len(v)}
            kf["o"] = {"x": [0.6] * len(v), "y": [0] * len(v)}
        frames.append(kf)
    return {"a": 1, "k": frames}


def group(*items, position=(0, 0), rotation=0):
    return {"ty": "gr", "it": [*items, {
        "ty": "tr", "p": static(list(position)), "a": static([0, 0]), "s": static([100, 100]),
        "r": static(rotation), "o": static(100), "sk": static(0), "sa": static(0)}]}


def ellipse(w, h=None):
    return {"ty": "el", "p": static([0, 0]), "s": static([w, h or w])}


def rect(w, h, radius):
    return {"ty": "rc", "p": static([0, 0]), "s": static([w, h]), "r": static(radius)}


def fill(color, opacity=100):
    return {"ty": "fl", "c": static(color), "o": static(opacity), "r": 1}


def stroke(color, width, opacity=100):
    return {"ty": "st", "c": static(color), "o": static(opacity), "w": static(width), "lc": 2, "lj": 2}


def layer(index, shapes, position=(100, 100), scale=None, rotation=None, opacity=None, start=0):
    return {
        "ddd": 0, "ind": index, "ty": 4, "nm": f"layer {index}", "sr": 1, "ao": 0, "bm": 0,
        "ip": 0, "op": FRAMES, "st": start,
        "ks": {
            "o": opacity or static(100),
            "r": rotation or static(0),
            "p": static([*position, 0]),
            "a": static([0, 0, 0]),
            "s": scale or static([100, 100, 100]),
        },
        "shapes": shapes,
    }


def animation(name, layers):
    return {"v": "5.7.4", "fr": 30, "ip": 0, "op": FRAMES, "w": SIZE, "h": SIZE, "nm": name,
            "ddd": 0, "assets": [], "layers": layers}


# ---- the animations -----------------------------------------------------------
def ingest():
    """Three document 'layers' dropping onto a stack, one after another."""
    layers = []
    for i, color in enumerate([CYAN, INDIGO, VIOLET]):
        y = 130 - i * 30
        start = i * 12
        layers.append(layer(
            i + 1, [group(rect(110, 24, 8), fill(color))], position=(100, y),
            scale=animated((start, [100, 0, 100]), (start + 12, [100, 110, 100]), (start + 18, [100, 100, 100])),
            opacity=animated((start, 0), (start + 8, 100), (75, 100), (FRAMES, 0)),
        ))
    return animation("ingest", layers)


def retrieve():
    """Radar: rings ripple out from a pulsing centre - 'searching the space'."""
    layers = [layer(1, [group(ellipse(26), fill(INDIGO))],
                    scale=animated((0, [100, 100, 100]), (45, [125, 125, 100]), (FRAMES, [100, 100, 100])))]
    for i in range(3):
        start = i * 30
        layers.append(layer(
            i + 2, [group(ellipse(40), stroke(CYAN, 5))],
            scale=animated((start, [60, 60, 100]), (start + 60, [420, 420, 100])),
            opacity=animated((start, 100), (start + 60, 0)),
        ))
    return animation("retrieve", layers)


def generate():
    """A rotating four-point spark (two crossed rounded bars) + a small orbiting dot."""
    spark = [group(rect(26, 120, 13), fill(VIOLET)), group(rect(120, 26, 13), fill(INDIGO))]
    return animation("generate", [
        layer(1, [group(ellipse(14), fill(AMBER), position=(0, -70))],
              rotation=animated((0, 0), (FRAMES, 360))),
        layer(2, spark, rotation=animated((0, 0), (FRAMES, 90)),
              scale=animated((0, [70, 70, 100]), (45, [95, 95, 100]), (FRAMES, [70, 70, 100]))),
    ])


def evaluate():
    """A score ring filling up (trim path) around a pulsing 'pass' dot."""
    ring_track = group(ellipse(130), stroke([0.89, 0.91, 0.94, 1], 12))
    ring = group(ellipse(130), stroke(EMERALD, 12),
                 {"ty": "tm", "s": static(0), "e": animated((0, 0), (60, 100), (FRAMES, 100)), "o": static(0), "m": 1})
    return animation("evaluate", [
        layer(1, [group(ellipse(40), fill(EMERALD))],
              scale=animated((50, [0, 0, 100]), (65, [120, 120, 100]), (75, [100, 100, 100]))),
        layer(2, [ring], rotation=static(-90)),
        layer(3, [ring_track]),
    ])


def orbit():
    """Hero / loading animation: three coloured dots orbiting a glowing core."""
    layers = [layer(1, [group(ellipse(46), fill(INDIGO))],
                    scale=animated((0, [90, 90, 100]), (45, [110, 110, 100]), (FRAMES, [90, 90, 100])))]
    for i, color in enumerate([CYAN, VIOLET, ROSE]):
        layers.append(layer(i + 2, [group(ellipse(18), fill(color), position=(0, -(50 + i * 14)))],
                            rotation=animated((0, i * 120), (FRAMES, i * 120 + 360 * (1 if i % 2 == 0 else -1)))))
    layers.append(layer(9, [group(ellipse(130), stroke(INDIGO, 2, opacity=25))]))
    return animation("orbit", layers)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for name, build in [("ingest", ingest), ("retrieve", retrieve), ("generate", generate),
                        ("evaluate", evaluate), ("orbit", orbit)]:
        (OUT / f"{name}.json").write_text(json.dumps(build()), encoding="utf-8")
        print(f"wrote static/lottie/{name}.json")
