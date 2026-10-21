"""
Sukoon — Adaptive difficulty engine.

IMPORTANT: This is a deliberately transparent, rule-based engine — NOT a
trained medical AI model. It is designed to be explainable to a caregiver
or judge in one sentence, and is architected so the `decide()` function
could later be swapped for a trained model without touching any caller.

Rules (difficulty is an integer 1-5):
  - High accuracy (>=0.85) AND fast response (<= FAST_MS)   -> increase
  - Low accuracy (<0.5) OR very slow response (> SLOW_MS)    -> decrease
  - Otherwise                                                 -> maintain

Difficulty is clamped to [1, 5].
"""
from dataclasses import dataclass

FAST_MS = 4000
SLOW_MS = 12000
HIGH_ACCURACY = 0.85
LOW_ACCURACY = 0.5

MIN_DIFFICULTY = 1
MAX_DIFFICULTY = 5


@dataclass
class AdaptiveResult:
    new_difficulty: int
    direction: str  # "increased" | "maintained" | "reduced"
    explanation_en: str
    explanation_as: str


def decide(current_difficulty: int, accuracy: float, avg_response_time_ms: int) -> AdaptiveResult:
    current_difficulty = max(MIN_DIFFICULTY, min(MAX_DIFFICULTY, current_difficulty))

    if accuracy >= HIGH_ACCURACY and avg_response_time_ms <= FAST_MS:
        new_difficulty = min(MAX_DIFFICULTY, current_difficulty + 1)
        direction = "increased" if new_difficulty > current_difficulty else "maintained"
        explanation_en = (
            "Activity difficulty increased — recent accuracy was high "
            f"({accuracy*100:.0f}%) and responses were quick. This keeps the activity "
            "appropriately challenging."
        )
        explanation_as = (
            "কাৰ্যকলাপৰ কঠিনতা বৃদ্ধি কৰা হ'ল — শুদ্ধতা উচ্চ আছিল আৰু সঁহাৰি দ্ৰুত আছিল।"
        )
    elif accuracy < LOW_ACCURACY or avg_response_time_ms > SLOW_MS:
        new_difficulty = max(MIN_DIFFICULTY, current_difficulty - 1)
        direction = "reduced" if new_difficulty < current_difficulty else "maintained"
        explanation_en = (
            "Activity difficulty reduced based on recent performance, to keep the "
            "activity comfortable and encouraging rather than frustrating."
        )
        explanation_as = (
            "শেহতীয়া কাৰ্যক্ষমতাৰ ওপৰত ভিত্তি কৰি কাৰ্যকলাপৰ কঠিনতা হ্ৰাস কৰা হ'ল।"
        )
    else:
        new_difficulty = current_difficulty
        direction = "maintained"
        explanation_en = (
            "Activity difficulty kept the same — recent performance has been steady."
        )
        explanation_as = "কাৰ্যকলাপৰ কঠিনতা একেই ৰখা হ'ল — শেহতীয়া কাৰ্যক্ষমতা স্থিৰ আছে।"

    return AdaptiveResult(
        new_difficulty=new_difficulty,
        direction=direction,
        explanation_en=explanation_en,
        explanation_as=explanation_as,
    )


_FALLBACK_EXPLANATION_EN = (
    "Activity difficulty kept unchanged — the adaptive engine received "
    "incomplete or inconsistent performance data this time, so it fell back "
    "to a safe, bounded default rather than guessing."
)
_FALLBACK_EXPLANATION_AS = "কাৰ্যকলাপৰ কঠিনতা অপৰিবৰ্তিত ৰখা হ'ল — অসম্পূৰ্ণ তথ্যৰ বাবে এটা সুৰক্ষিত ডিফল্ট ব্যৱহাৰ কৰা হ'ল।"


def safe_decide(current_difficulty, accuracy, avg_response_time_ms) -> AdaptiveResult:
    """Guarded entry point for every caller (legacy sync + the offline care
    ledger). `decide()` above is a pure rule engine, not a trained model, so
    it cannot itself "hallucinate" — but its *inputs* can still be missing,
    malformed, or contradictory (a replayed/offline event, a future client
    bug, a hand-edited test fixture). This wrapper is the one place that
    guarantees: bad input or an unexpected internal error never raises and
    never produces an out-of-range difficulty — it always falls back to
    "keep the current difficulty" instead. This function touches only
    difficulty (a cognitive-activity tuning value); by construction it never
    reads or writes anything reminder/medication/safety-related, so an
    adaptive-engine failure can never cascade into a safety decision."""
    try:
        current = int(current_difficulty)
        if not (MIN_DIFFICULTY <= current <= MAX_DIFFICULTY):
            raise ValueError(f"current_difficulty {current_difficulty!r} out of range")
        acc = float(accuracy)
        rt = float(avg_response_time_ms)
        if not (0.0 <= acc <= 1.0) or rt < 0 or rt != rt:  # rt != rt catches NaN
            raise ValueError("accuracy/avg_response_time_ms out of range or NaN")

        result = decide(current, acc, rt)

        if not (MIN_DIFFICULTY <= result.new_difficulty <= MAX_DIFFICULTY):
            raise ValueError(f"decide() produced out-of-range difficulty {result.new_difficulty}")
        if result.direction not in ("increased", "maintained", "reduced"):
            raise ValueError(f"decide() produced unknown direction {result.direction!r}")
        return result
    except Exception:
        safe_current = current_difficulty if isinstance(current_difficulty, int) and MIN_DIFFICULTY <= current_difficulty <= MAX_DIFFICULTY else MIN_DIFFICULTY
        return AdaptiveResult(
            new_difficulty=safe_current,
            direction="maintained",
            explanation_en=_FALLBACK_EXPLANATION_EN,
            explanation_as=_FALLBACK_EXPLANATION_AS,
        )
