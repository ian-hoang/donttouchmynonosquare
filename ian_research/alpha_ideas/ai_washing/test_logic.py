"""Hand-checked cases for the pieces of run.py / features.py that decide timing and counts.

Run from the repo root:  uv run python alpha_ideas/ai_washing/test_logic.py   (no network, no market data)
"""
import numpy as np
import pandas as pd

import features as F
import run as R


def test_day0():
    cal = pd.DatetimeIndex(pd.bdate_range("2024-01-08", "2024-01-19")).astype("datetime64[ns]")  # Mon..Fri x2
    acc = pd.Series(pd.to_datetime([
        "2024-01-08 08:00",  # Mon pre-open      -> Mon (index 0)
        "2024-01-08 16:00",  # Mon at 16:00      -> Mon (index 0)
        "2024-01-08 16:01",  # Mon after close   -> Tue (index 1)
        "2024-01-13 10:00",  # Saturday          -> Mon 15th (index 5)
        "2024-01-12 17:30",  # Fri after close   -> Mon 15th (index 5)
    ])).astype("datetime64[ns]")
    got = R.day0_of(acc, cal)
    assert list(got) == [0, 0, 1, 5, 5], got


def test_calendar_time():
    cal = pd.DatetimeIndex(pd.bdate_range("2024-01-01", "2024-02-29")).astype("datetime64[ns]")
    ev = pd.DataFrame({"w_start": [0, 2], "ar": [np.array([0.01, 0.01, 0.01]), np.array([-0.03, 0.0])]})
    m, d = R.calendar_time(ev, cal, months=("2024-01", "2024-02"), min_held=0)
    # day 0: only event A (0.01); day 1: A (0.01); day 2: A 0.01 and B -0.03 -> mean -0.01; day 3: B 0.0
    assert np.allclose(d["ar"].iloc[:4].to_numpy(), [0.01, 0.01, -0.01, 0.0])
    assert np.isclose(m.loc[pd.Period("2024-01"), "ar"], 0.01)  # 0.01 + 0.01 - 0.01 + 0.0
    assert m.loc[pd.Period("2024-01"), "entries"] == 2
    n_jan = (cal.month == 1).sum()
    assert np.isclose(m.loc[pd.Period("2024-01"), "held"], (1 + 1 + 2 + 1) / n_jan)
    assert np.isnan(m.loc[pd.Period("2024-02"), "ar"])  # nothing held in February


def test_annual_pair():
    fa = pd.DataFrame({
        "concept": ["PaymentsToAcquirePropertyPlantAndEquipment"] * 4,
        "start": pd.to_datetime(["2023-01-01", "2022-01-01", "2021-01-01", "2023-10-01"]),
        "end": pd.to_datetime(["2023-12-31", "2022-12-31", "2021-12-31", "2023-12-31"]),
        "val": [100.0, 80.0, 60.0, 30.0],
    })
    fa["dur"] = (fa["end"] - fa["start"]).dt.days
    fa = fa[(fa["dur"] >= 330) & (fa["dur"] <= 400)]  # the quarterly fact is dropped, as in load_facts
    cur, prior, fy = R.annual_pair(fa, "PaymentsToAcquirePropertyPlantAndEquipment")
    assert (cur, prior, fy) == (100.0, 80.0, pd.Timestamp("2023-12-31"))
    assert R.annual_pair(fa, "ResearchAndDevelopmentExpense") is None


def test_counts():
    text = F.html_to_text(
        "<p>We launched AI-powered tools &amp; an A.I. roadmap with OpenAI. GenAI and ChatGPT pilots; "
        "generative AI agents. AIG, MAID, PAI and Ai are not AI-terms here except the last word: AI.</p>"
        "<div>Artificial&nbsp;Intelligence and machine learning; large language models (LLMs); GPT-4o; "
        "agentic workflows; neural networks; deep learning.</div>")
    c = F.count(text)
    assert c["n_AI"] == 4, c          # AI-powered, generative AI, "AI-terms", final "AI"
    assert c["n_A.I."] == 1 and c["n_OpenAI"] == 1 and c["n_GenAI"] == 1, c
    assert c["n_chatgpt"] == 1 and "n_GPT" not in c, c   # GPT dropped (oil & gas "gathering, processing and transportation")
    assert c["n_LLM"] == 1 and c["n_large language model"] == 1, c
    assert c["n_artificial intelligence"] == 1 and c["n_machine learning"] == 1, c
    assert c["n_agentic"] == 1 and c["n_neural network"] == 1 and c["n_deep learning"] == 1, c
    assert c["ai_strict"] == 5 and c["ai_full"] == 15, c
    assert not c["ai_redefined"]


def test_redefined():
    tyson = F.count("Risks include livestock disease (such as avian influenza (AI) or ASF). We also use AI tools.")
    assert tyson["ai_redefined"] and tyson["n_AI"] == 0, tyson
    aap = F.count("certain converted Autopart International (AI) stores; AI sales grew.")
    assert aap["ai_redefined"] and aap["n_AI"] == 0, aap
    onc = F.count("1L = frontline; AI = aromatase inhibitor; CDK46i")
    assert onc["ai_redefined"] and onc["n_AI"] == 0, onc
    real = F.count("We expanded our use of artificial intelligence (AI) and generative AI.")
    assert not real["ai_redefined"] and real["n_AI"] == 2 and real["n_artificial intelligence"] == 1, real


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
