"""Publications the world pilot takes its figures from, with links.

Every movement (event) and estimate of the pilot names the publications behind it as
``{"title", "url"}`` items in its ``sources`` attribute; the balance shows them next to
each flow. Figures computed from them say so in their reference text.
"""

SOURCES: dict[str, tuple[str, str | None]] = {
    # Saudi national statistics
    "opec-asb-2000": (
        "OPEC Annual Statistical Bulletin 2000",
        "https://www.opec.org/assets/assetdb/asb-2000.pdf",
    ),
    "opec-asb-2004": (
        "OPEC Annual Statistical Bulletin 2004",
        "https://www.opec.org/assets/assetdb/asb-2004.pdf",
    ),
    "opec-asb-2005": (
        "OPEC Annual Statistical Bulletin 2005",
        "https://www.opec.org/assets/assetdb/asb-2005.pdf",
    ),
    "opec-asb-2008": (
        "OPEC Annual Statistical Bulletin 2008",
        "https://www.opec.org/assets/assetdb/asb-2008.pdf",
    ),
    "opec-asb-2009": (
        "OPEC Annual Statistical Bulletin 2009",
        "https://www.opec.org/assets/assetdb/asb-2009.pdf",
    ),
    "opec-asb-2014": (
        "OPEC Annual Statistical Bulletin 2014",
        "https://www.opec.org/assets/assetdb/asb-2014.pdf",
    ),
    "opec-asb-2015": (
        "OPEC Annual Statistical Bulletin 2015",
        "https://www.opec.org/assets/assetdb/asb-2015.pdf",
    ),
    "opec-asb-2017": (
        "OPEC Annual Statistical Bulletin 2017",
        "https://www.opec.org/assets/assetdb/asb-2017.pdf",
    ),
    "opec-asb-2019": (
        "OPEC Annual Statistical Bulletin 2019",
        "https://www.opec.org/assets/assetdb/asb-2019.pdf",
    ),
    "opec-asb-2021": (
        "OPEC Annual Statistical Bulletin 2021",
        "https://www.opec.org/assets/assetdb/asb-2021.pdf",
    ),
    "opec-asb-2020": (
        "OPEC Annual Statistical Bulletin 2020",
        "https://asb.opec.org/",
    ),
    "opec-asb-2022": (
        "OPEC Annual Statistical Bulletin 2022",
        "https://www.opec.org/assets/assetdb/asb-2022.pdf",
    ),
    "opec-asb-2023": (
        "OPEC Annual Statistical Bulletin 2023",
        "https://asb.opec.org/",
    ),
    "opec-asb-2025": (
        "OPEC Annual Statistical Bulletin 2025",
        "https://asb.opec.org/",
    ),
    "opec-asb-2026": (
        "OPEC Annual Statistical Bulletin 2026",
        "https://publications.opec.org/ASSETS/assetdb/asb-2026.pdf",
    ),
    "jodi": (
        "JODI Oil World Database, annual primary data",
        "https://www.jodidata.org/oil/database/data-downloads.aspx",
    ),
    "gastat-2025": (
        "GASTAT, Oil and Gas Statistics 2025",
        "https://stats.gov.sa/documents/20117/2435281/%E2%80%8F%E2%80%8FOil+and+Gas+Statistics+2025+EN+(1).pdf/bec93bd3-47df-4ffd-3915-61561a07c200",
    ),
    "arabnews-2021": (
        "Arab News: Saudi crude oil exports fell in 2021 (OPEC data)",
        "https://www.arabnews.com/node/2028351",
    ),
    "spglobal-2021": (
        "S&P Global: Saudi refining capacity rises 14% in 2021 (OPEC ASB)",
        "https://www.spglobal.com/commodity-insights/en/news-research/latest-news/crude-oil/062822-saudi-refining-capacity-rises-14-in-2021",
    ),
    # Saudi Aramco
    "aramco-bond-2019": (
        "Saudi Aramco bond prospectus, April 2019 (as reported: Ghawar 48.25 bn bbl, MSC 3.8 mb/d)",
        "https://blog.gorozen.com/blog/what-saudi-aramcos-bond-offering-says-about-the-ghawar-oil-field",
    ),
    "aramco-ara-2019": (
        "Saudi Aramco Annual Report 2019",
        "https://www.aramco.com/-/media/publications/corporate-reports/annual-reports/saudi-aramco-ara-2019-english.pdf",
    ),
    "aramco-ara-2020": (
        "Saudi Aramco Annual Report 2020",
        "https://www.aramco.com/-/media/publications/corporate-reports/annual-reports/saudi-aramco-ara-2020-english.pdf",
    ),
    "aramco-ara-2022": (
        "Saudi Aramco Annual Report 2022",
        "https://www.aramco.com/-/media/publications/corporate-reports/annual-reports/saudi-aramco-ara-2022-english.pdf",
    ),
    "aramco-ara-2024": (
        "Saudi Aramco Annual Report 2024, results",
        "https://www.aramco.com/-/media/publications/corporate-reports/reports-and-presentations/2024/fy/sections/ara-2024-results-english.pdf",
    ),
    "aramco-ara-2025": (
        "Saudi Aramco Annual Report 2025, results",
        "https://www.aramco.com/-/media/publications/corporate-reports/reports-and-presentations/2025/fy/sections/ara-2025-results-english.pdf",
    ),
    # India
    "argus-2021-india": (
        "Argus Media: Indian refiners limit cuts to May Saudi crude imports (2019: 855,000 b/d; 2020: 753,000 b/d)",
        "https://www.argusmedia.com/en/news/2203801-indian-refiners-limit-cuts-to-may-saudi-crude-imports",
    ),
    "informist-2024-india": (
        "Informist MoneyWire: India's 2024 crude oil imports (Saudi Arabia 625,997 b/d)",
        "https://informistmedia.com/MoneyWire/27095/India-s-2024-crude-oil-imports-up-3-37-at-1-78-bln-barrels-Russia-s-share-36-3-37-",
    ),
    "eoi-riyadh": (
        "Embassy of India, Riyadh: India-Saudi Arabia economic and commercial brief (crude imports by fiscal year)",
        "https://www.eoiriyadh.gov.in/page/india-saudi-arabia-economic-and-commercial-brief/",
    ),
    "aramco-prospectus-2019": (
        "Saudi Aramco Global Medium Term Note Programme, Base Prospectus, 1 April 2019 (Ghawar 48.25 bn bbl, MSC 3.8 mb/d)",
        "https://www.rns-pdf.londonstockexchange.com/rns/6727U_1-2019-4-1.pdf",
    ),
    # Ghawar history
    "geoexpro-2010": (
        "Sorkhabi R., The King of Giant Fields, GeoExPro 7(4), 2010 (Oil & Gas Journal data)",
        "https://web.archive.org/web/20200816221552/https://www.geoexpro.com/articles/2010/04/the-king-of-giant-fields",
    ),
    "aramcoworld-1973": (
        "AramcoWorld, May/June 1973: Oscar for an Oilfield",
        "https://archive.aramcoworld.com/issue/197306/oscar.for.an.oilfield.htm",
    ),
    "iea-weo-2005": (
        "IEA, World Energy Outlook 2005: Middle East and North Africa Insights (Box 16.1, Table 16.7)",
        "https://iea.blob.core.windows.net/assets/5516c403-58ef-4b4f-92e6-95161a1a5f34/WorldEnergyOutlook2005-MiddleEastandNorthAfricaInsights.pdf",
    ),
    "iea-weo-2008": (
        "IEA, World Energy Outlook 2008 (Table 10.1, Box 10.4)",
        "https://www.iea.org/files/89d1f68c-f4bf-4597-805f-901cfa6ce889/weo2008.pdf",
    ),
    "afifi-2004": (
        "Afifi A.M., Ghawar: the anatomy of the world's largest oil field, AAPG Search and Discovery 20026, 2004",
        "https://www.searchanddiscovery.com/documents/2004/afifi01/index.htm",
    ),
    "aapg-2005": (
        "Durham L.S., The Elephant of All Elephants, AAPG Explorer, January 2005",
        "https://web.archive.org/web/20060302145331/http://www.aapg.org/explorer/2005/01jan/ghawar.cfm",
    ),
    "un-comtrade-india": (
        "UN Comtrade: India's imports of crude oil (HS 2709) from Saudi Arabia, net weight",
        "https://comtradeplus.un.org/TradeFlow?Frequency=A&Flows=M&CommodityCodes=2709&Partners=682&Reporters=699",
    ),
    # Model assumptions
    "model-voyages": ("Model assumption: vessels, sea lane and voyage timing are schematic", None),
}


def source(key: str) -> dict:
    """A source as stored on events and estimates."""
    title, url = SOURCES[key]
    return {"title": title, "url": url}


def sources(*keys: str) -> list[dict]:
    seen: list[dict] = []
    for key in keys:
        item = source(key)
        if item not in seen:
            seen.append(item)
    return seen
