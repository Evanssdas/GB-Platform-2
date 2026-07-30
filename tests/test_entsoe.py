import pandas as pd

from gb_platform_v2.data.entsoe import (
    combine_directional_flows,
    parse_day_ahead_prices,
    parse_physical_flows,
)


PRICE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Publication_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3">
  <createdDateTime>2026-07-29T12:00Z</createdDateTime>
  <TimeSeries>
    <mRID>price-series</mRID>
    <currency_Unit.name>EUR</currency_Unit.name>
    <price_Measure_Unit.name>MWH</price_Measure_Unit.name>
    <Period>
      <timeInterval><start>2026-07-30T00:00Z</start><end>2026-07-30T02:00Z</end></timeInterval>
      <resolution>PT60M</resolution>
      <Point><position>1</position><price.amount>-10.0</price.amount></Point>
      <Point><position>2</position><price.amount>50.0</price.amount></Point>
    </Period>
  </TimeSeries>
</Publication_MarketDocument>
"""


FLOW_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Publication_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3">
  <createdDateTime>2026-07-30T03:00Z</createdDateTime>
  <TimeSeries>
    <mRID>flow-series</mRID>
    <in_Domain.mRID>GB</in_Domain.mRID>
    <out_Domain.mRID>FR</out_Domain.mRID>
    <quantity_Measure_Unit.name>MAW</quantity_Measure_Unit.name>
    <Period>
      <timeInterval><start>2026-07-30T00:00Z</start><end>2026-07-30T01:00Z</end></timeInterval>
      <resolution>PT30M</resolution>
      <Point><position>1</position><quantity>1000</quantity></Point>
      <Point><position>2</position><quantity>900</quantity></Point>
    </Period>
  </TimeSeries>
</Publication_MarketDocument>
"""


def test_hourly_prices_are_expanded_to_half_hourly_and_keep_negative_values():
    frame = parse_day_ahead_prices(PRICE_XML)
    assert len(frame) == 4
    assert frame["price_eur_mwh"].tolist() == [-10.0, -10.0, 50.0, 50.0]
    assert frame["timestamp"].diff().dropna().eq(pd.Timedelta(minutes=30)).all()


def test_directional_flow_sign_is_positive_into_gb():
    inbound = parse_physical_flows(FLOW_XML)
    outbound = inbound.copy()
    outbound["flow_mw"] = [100.0, 100.0]
    combined = combine_directional_flows(inbound, outbound, "france")
    assert combined["france_net_import_mw"].tolist() == [900.0, 800.0]
