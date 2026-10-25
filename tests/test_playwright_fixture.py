from fixtures.playwright_recommend import recommend


def test_dummy_world_recommendation_is_stable():
    first = recommend()
    second = recommend()
    assert first == second
    assert first["top"] == "RELIANCE.NSE"
    ranked = {row["symbol"]: row for row in first["recommendations"]}
    assert ranked["RELIANCE.NSE"]["score"] == 79.4
    assert ranked["RELIANCE.NSE"]["decision"] == "review"
    assert ranked["RELIANCE.NSE"]["rank"] == 1
    assert ranked["TCS.NSE"]["score"] == 62.0
    assert ranked["TCS.NSE"]["decision"] == "review"
    assert ranked["TINY.NSE"]["score"] == 42.5
    assert ranked["TINY.NSE"]["decision"] == "skip"
    assert ranked["TINY.NSE"]["headline"] == "No headlines"
