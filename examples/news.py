"""Run: APPRESS_API_KEY=... python examples/news.py

NOTE: spends real API credit.
"""

from appress import Appress, InsufficientCreditError, get_result_text

with Appress() as appress:
    try:
        news = appress.generations.create_and_wait(
            feature_type="NEWS",
            input_text="Appress announced a new version of its AI-powered content generation platform.",
            feature_params={"news_lang": "en", "tone": "Objective", "news_category": "technology"},
            on_progress=lambda g: print(g["status"], g["progress"]["step"] or ""),
        )
    except InsufficientCreditError:
        print("Not enough API credit; nothing was charged.")
    else:
        if news["status"] == "COMPLETED":
            print(get_result_text(news.get("result")))
        else:
            print(news["status"], news.get("error"))
