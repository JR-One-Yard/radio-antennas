from meteor_lease.heard import icao_from_dump1090, icao_from_rtl_adsb_line


def test_icao_from_dump1090():
    rows = icao_from_dump1090(
        {
            "aircraft": [
                {"hex": "7c6d2a", "flight": "QFA441 ", "alt_baro": 37000, "gs": 430},
                {"hex": "bad", "flight": "nope"},
            ]
        }
    )
    assert rows[0]["hex"] == "7c6d2a"
    assert rows[0]["flight"] == "QFA441"
    assert len(rows) == 1


def test_icao_from_rtl_adsb_star_line():
    assert icao_from_rtl_adsb_line("*8D7C6D2A990D9A50000000;") == "7c6d2a"
    assert icao_from_rtl_adsb_line("noise") is None
