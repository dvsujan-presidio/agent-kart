from datetime import datetime
from zoneinfo import ZoneInfo

from voice.speech_format import number_to_words, speak_money, speak_time

IST = ZoneInfo("Asia/Kolkata")


def test_words():
    assert number_to_words(2810) == "two thousand eight hundred ten"
    assert number_to_words(125000) == "one lakh twenty five thousand"
    assert number_to_words(0) == "zero"


def test_money():
    assert speak_money(281000, "INR") == "two thousand eight hundred ten rupees"
    assert speak_money(41250, "USD") == "four hundred twelve dollars fifty cents"


def test_time():
    now = datetime(2026, 10, 17, 12, tzinfo=IST)
    assert speak_time(datetime(2026, 10, 18, 17, tzinfo=IST), now) == "5 PM tomorrow"
    assert speak_time(datetime(2026, 10, 17, 9, 30, tzinfo=IST), now) == "9:30 AM today"
