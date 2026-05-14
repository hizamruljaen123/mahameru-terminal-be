"""
PRIMARY RSS SOURCE REGISTRY — ASETPEDIA OSINT ENGINE
=====================================================
Berisi sumber berita primer (bukan aggregator) untuk setiap kategori strategis.
Sumber ini diprioritaskan di atas dynamic Google News injection.

Format setiap entri:
{
    'name'    : Nama display sumber
    'url'     : URL RSS feed langsung
    'category': Kategori uppercase sesuai PRIORITY_CATEGORIES
    'lang'    : 'id' atau 'en'
    'trust'   : 1-10 (10 = paling terpercaya, seperti Reuters, Bloomberg)
}
"""

PRIMARY_SOURCES = [

    # =========================================================
    # TIER 1 — INDONESIA & CORE NATIONAL
    # =========================================================
    {'name': 'Antara News', 'url': 'https://www.antaranews.com/rss/terkini.xml', 'category': 'INDONESIA', 'lang': 'id', 'trust': 9},
    {'name': 'Kompas', 'url': 'https://rss.kompas.com/rss2/kompas-nasional', 'category': 'INDONESIA', 'lang': 'id', 'trust': 9},
    {'name': 'Detik.com', 'url': 'https://news.detik.com/rss', 'category': 'INDONESIA', 'lang': 'id', 'trust': 8},
    {'name': 'Tempo', 'url': 'https://rss.tempo.co/', 'category': 'INDONESIA', 'lang': 'id', 'trust': 9},
    {'name': 'CNN Indonesia', 'url': 'https://www.cnnindonesia.com/nasional/rss', 'category': 'INDONESIA', 'lang': 'id', 'trust': 8},
    {'name': 'BBC Indonesia', 'url': 'https://feeds.bbci.co.uk/indonesian/rss.xml', 'category': 'INDONESIA', 'lang': 'id', 'trust': 10},
    {'name': 'VOA Indonesia', 'url': 'https://www.voaindonesia.com/api/zmgqoe-eioi', 'category': 'INDONESIA', 'lang': 'id', 'trust': 9},

    # =========================================================
    # TIER 1 — BUSINESS & ECONOMY
    # =========================================================
    {'name': 'CNBC Indonesia', 'url': 'https://www.cnbcindonesia.com/rss', 'category': 'BUSINESS', 'lang': 'id', 'trust': 9},
    {'name': 'Bisnis.com', 'url': 'https://bisnis.com/feed', 'category': 'BUSINESS', 'lang': 'id', 'trust': 9},
    {'name': 'Kontan', 'url': 'https://rss.kontan.co.id/category/bisnis', 'category': 'BUSINESS', 'lang': 'id', 'trust': 8},
    {'name': 'Reuters Business', 'url': 'https://feeds.reuters.com/reuters/businessNews', 'category': 'BUSINESS', 'lang': 'en', 'trust': 10},
    {'name': 'Bloomberg Markets', 'url': 'https://feeds.bloomberg.com/markets/news.rss', 'category': 'BUSINESS', 'lang': 'en', 'trust': 10},
    {'name': 'Financial Times', 'url': 'https://www.ft.com/rss/home', 'category': 'ECONOMY', 'lang': 'en', 'trust': 10},
    {'name': 'The Economist', 'url': 'https://www.economist.com/finance-and-economics/rss.xml', 'category': 'ECONOMY', 'lang': 'en', 'trust': 10},
    {'name': 'Reuters Economy', 'url': 'https://feeds.reuters.com/reuters/economicNews', 'category': 'ECONOMY', 'lang': 'en', 'trust': 10},
    {'name': 'Ekonomi Bisnis.com', 'url': 'https://ekonomi.bisnis.com/feed', 'category': 'EKONOMI', 'lang': 'id', 'trust': 8},
    {'name': 'Republika Ekonomi', 'url': 'https://republika.co.id/rss/ekonomi', 'category': 'EKONOMI', 'lang': 'id', 'trust': 8},
    {'name': 'Bareksa', 'url': 'https://www.bareksa.com/rss/news', 'category': 'INVESTASI', 'lang': 'id', 'trust': 8},
    {'name': 'IDX Channel', 'url': 'https://www.idxchannel.com/rss', 'category': 'INVESTASI', 'lang': 'id', 'trust': 8},

    # =========================================================
    # TIER 1 — POLITICS & PEMERINTAHAN
    # =========================================================
    {'name': 'Reuters Politics', 'url': 'https://feeds.reuters.com/reuters/politicsNews', 'category': 'POLITICS', 'lang': 'en', 'trust': 10},
    {'name': 'Antara Politik', 'url': 'https://www.antaranews.com/rss/politik.xml', 'category': 'POLITICS', 'lang': 'id', 'trust': 9},
    {'name': 'Setkab', 'url': 'https://setkab.go.id/feed/', 'category': 'PEMERINTAHAN', 'lang': 'id', 'trust': 10},
    {'name': 'Kemenkeu', 'url': 'https://www.kemenkeu.go.id/rss', 'category': 'PEMERINTAHAN', 'lang': 'id', 'trust': 10},

    # =========================================================
    # TIER 2 — GEOPOLITICS & INTELLIGENCE
    # =========================================================
    {'name': 'Reuters World', 'url': 'https://feeds.reuters.com/reuters/worldNews', 'category': 'INTERNATIONAL', 'lang': 'en', 'trust': 10},
    {'name': 'BBC World', 'url': 'http://feeds.bbci.co.uk/news/world/rss.xml', 'category': 'WORLD', 'lang': 'en', 'trust': 10},
    {'name': 'Al Jazeera', 'url': 'https://www.aljazeera.com/xml/rss/all.xml', 'category': 'WORLD', 'lang': 'en', 'trust': 9},
    {'name': 'The Diplomat', 'url': 'https://thediplomat.com/feed/', 'category': 'GEOPOLITICS', 'lang': 'en', 'trust': 9},
    {'name': 'Foreign Policy', 'url': 'https://foreignpolicy.com/feed/', 'category': 'GEOPOLITICS', 'lang': 'en', 'trust': 10},
    {'name': 'Stratfor', 'url': 'https://worldview.stratfor.com/rss.xml', 'category': 'INTELLIGENCE', 'lang': 'en', 'trust': 10},
    {'name': 'Jane\'s Defence', 'url': 'https://www.janes.com/feeds/news', 'category': 'INTELLIGENCE', 'lang': 'en', 'trust': 10},
    {'name': 'Bellingcat', 'url': 'https://www.bellingcat.com/feed/', 'category': 'INTELLIGENCE', 'lang': 'en', 'trust': 9},

    # =========================================================
    # TIER 2 — RISK & SUPPLY CHAIN
    # =========================================================
    {'name': 'Supply Chain Dive', 'url': 'https://www.supplychaindive.com/feeds/news/', 'category': 'SUPPLY CHAIN', 'lang': 'en', 'trust': 8},
    {'name': 'Risk.net', 'url': 'https://www.risk.net/rss', 'category': 'RISK MANAGEMENT', 'lang': 'en', 'trust': 9},
    {'name': 'Kroll Risk', 'url': 'https://www.kroll.com/en/insights/publications/rss', 'category': 'BUSINESS RISK', 'lang': 'en', 'trust': 8},

    # =========================================================
    # TIER 3 — LEGAL & HUKUM
    # =========================================================
    {'name': 'Hukum Online', 'url': 'https://www.hukumonline.com/feeds/berita/', 'category': 'HUKUM BISNIS', 'lang': 'id', 'trust': 9},
    {'name': 'BPKN', 'url': 'https://bpkn.go.id/feeds', 'category': 'HUKUM BISNIS', 'lang': 'id', 'trust': 9},
    {'name': 'Reuters Legal', 'url': 'https://feeds.reuters.com/reuters/legal', 'category': 'TRADE LAW', 'lang': 'en', 'trust': 10},
    {'name': 'Lexology', 'url': 'https://www.lexology.com/rss.ashx', 'category': 'LEGAL COMPLIANCE', 'lang': 'en', 'trust': 8},
    {'name': 'Global Arbitration Review', 'url': 'https://globalarbitrationreview.com/rss', 'category': 'ARBITRATION', 'lang': 'en', 'trust': 9},

    # =========================================================
    # TIER 4 — MILITARY & DEFENSE
    # =========================================================
    {'name': 'Defense News', 'url': 'https://www.defensenews.com/rss/', 'category': 'DEFENSE NEWS', 'lang': 'en', 'trust': 9},
    {'name': 'The War Zone', 'url': 'https://www.thedrive.com/the-war-zone/rss/', 'category': 'MILITARY NEWS', 'lang': 'en', 'trust': 9},
    {'name': 'Naval Today', 'url': 'https://navaltoday.com/feed/', 'category': 'NAVAL NEWS', 'lang': 'en', 'trust': 8},
    {'name': 'Army Times', 'url': 'https://www.armytimes.com/arc/outboundfeeds/rss/', 'category': 'ARMY NEWS', 'lang': 'en', 'trust': 8},
    {'name': 'Breaking Defense', 'url': 'https://breakingdefense.com/feed/', 'category': 'DEFENSE NEWS', 'lang': 'en', 'trust': 9},
    {'name': 'Defensanet (Spain-ASEAN)', 'url': 'https://www.infodefensa.com/feed', 'category': 'DEFENSE NEWS', 'lang': 'en', 'trust': 7},

    # =========================================================
    # TIER 4 — ENERGY & INDUSTRIAL
    # =========================================================
    {'name': 'Reuters Energy', 'url': 'https://feeds.reuters.com/reuters/energy', 'category': 'ENERGY', 'lang': 'en', 'trust': 10},
    {'name': 'Oilprice.com', 'url': 'https://oilprice.com/rss/main', 'category': 'ENERGY', 'lang': 'en', 'trust': 8},
    {'name': 'S&P Global Energy', 'url': 'https://www.spglobal.com/commodityinsights/en/rss-feed/oil', 'category': 'ENERGY', 'lang': 'en', 'trust': 9},
    {'name': 'Mining.com', 'url': 'https://www.mining.com/feed/', 'category': 'MINING', 'lang': 'en', 'trust': 8},
    {'name': 'Manufacturing.net', 'url': 'https://www.manufacturing.net/rss/', 'category': 'MANUFACTURING', 'lang': 'en', 'trust': 8},
    {'name': 'Aviation Week', 'url': 'https://aviationweek.com/rss.xml', 'category': 'AVIATION', 'lang': 'en', 'trust': 9},
    {'name': 'Katadata Energi', 'url': 'https://katadata.co.id/tag/energi/feed', 'category': 'ENERGI', 'lang': 'id', 'trust': 8},

    # =========================================================
    # TIER 5 — TECHNOLOGY & CYBER
    # =========================================================
    {'name': 'TechCrunch', 'url': 'https://techcrunch.com/feed/', 'category': 'TECHNOLOGY', 'lang': 'en', 'trust': 8},
    {'name': 'The Verge', 'url': 'https://www.theverge.com/rss/index.xml', 'category': 'TECHNOLOGY', 'lang': 'en', 'trust': 8},
    {'name': 'Krebs on Security', 'url': 'https://krebsonsecurity.com/feed/', 'category': 'CYBER SECURITY', 'lang': 'en', 'trust': 10},
    {'name': 'Dark Reading', 'url': 'https://www.darkreading.com/rss_simple.asp', 'category': 'CYBER SECURITY', 'lang': 'en', 'trust': 9},
    {'name': 'BleepingComputer', 'url': 'https://www.bleepingcomputer.com/feed/', 'category': 'CYBER SECURITY', 'lang': 'en', 'trust': 9},
    {'name': 'Tekno Kompas', 'url': 'https://tekno.kompas.com/rss', 'category': 'TEKNOLOGI', 'lang': 'id', 'trust': 8},

    # --- CYBER INTEL (GOVERNMENT & AUTHORITIES) ---
    {'name': 'CISA Advisories', 'url': 'https://www.cisa.gov/cybersecurity-advisories/all.xml', 'category': 'CYBER INTEL', 'lang': 'en', 'trust': 10},
    {'name': 'NCSC UK Alerts', 'url': 'https://www.ncsc.gov.uk/api/1/services/reporting/rss/all-alerts-advisories', 'category': 'CYBER INTEL', 'lang': 'en', 'trust': 10},
    {'name': 'ENISA News', 'url': 'https://www.enisa.europa.eu/news/enisa-news/RSS', 'category': 'CYBER INTEL', 'lang': 'en', 'trust': 10},
    {'name': 'CERT NZ', 'url': 'https://www.cert.govt.nz/it-specialists/advisories/rss', 'category': 'CYBER INTEL', 'lang': 'en', 'trust': 9},
    {'name': 'Cyber GC Canada', 'url': 'https://cyber.gc.ca/en/rss/alerts-advisories', 'category': 'CYBER INTEL', 'lang': 'en', 'trust': 10},
    {'name': 'AusCERT', 'url': 'https://www.auscert.org.au/blog/rss', 'category': 'CYBER INTEL', 'lang': 'en', 'trust': 9},
    {'name': 'JPCERT', 'url': 'https://www.jpcert.or.jp/english/at/rss.xml', 'category': 'CYBER INTEL', 'lang': 'en', 'trust': 9},

    # --- STRATEGIC THREAT INTELLIGENCE ---
    {'name': 'Mandiant Blog', 'url': 'https://www.mandiant.com/resources/blog/rss.xml', 'category': 'CYBER INTEL', 'lang': 'en', 'trust': 10},
    {'name': 'Kaspersky Securelist', 'url': 'https://securelist.com/feed/', 'category': 'CYBER INTEL', 'lang': 'en', 'trust': 10},
    {'name': 'CrowdStrike Blog', 'url': 'https://www.crowdstrike.com/blog/feed/', 'category': 'CYBER INTEL', 'lang': 'en', 'trust': 10},
    {'name': 'Unit 42 Unit', 'url': 'https://unit42.paloaltonetworks.com/feed/', 'category': 'CYBER INTEL', 'lang': 'en', 'trust': 9},
    {'name': 'Microsoft Threat Intel', 'url': 'https://www.microsoft.com/en-us/security/blog/topic/threat-intelligence/feed/', 'category': 'CYBER INTEL', 'lang': 'en', 'trust': 10},
    {'name': 'Dragos Blog', 'url': 'https://www.dragos.com/blog/feed/', 'category': 'CYBER INTEL', 'lang': 'en', 'trust': 9},
    {'name': 'SentinelOne', 'url': 'https://www.sentinelone.com/blog/rss/', 'category': 'CYBER INTEL', 'lang': 'en', 'trust': 9},
    {'name': 'Recorded Future', 'url': 'https://www.recordedfuture.com/blog/rss.xml', 'category': 'CYBER INTEL', 'lang': 'en', 'trust': 10},

    # --- CYBER GEOPOLITICS & GLOBAL ---
    {'name': 'CCDCOE News', 'url': 'https://ccdcoe.org/news/rss', 'category': 'CYBER INTEL', 'lang': 'en', 'trust': 9},
    {'name': 'The Hacker News', 'url': 'https://feeds.feedburner.com/TheHackersNews', 'category': 'CYBER INTEL', 'lang': 'en', 'trust': 8},
    {'name': 'SANS ISC', 'url': 'https://isc.sans.edu/rssfeed.xml', 'category': 'CYBER INTEL', 'lang': 'en', 'trust': 9},
    {'name': 'Infosecurity Magazine', 'url': 'https://www.infosecurity-magazine.com/rss/news/', 'category': 'CYBER INTEL', 'lang': 'en', 'trust': 8},
    {'name': 'SC Magazine', 'url': 'https://www.scmagazine.com/rss', 'category': 'CYBER INTEL', 'lang': 'en', 'trust': 8},

    # =========================================================
    # TIER 5 — CRYPTO & FINANCE
    # =========================================================
    {'name': 'CoinDesk', 'url': 'https://www.coindesk.com/arc/outboundfeeds/rss/', 'category': 'CRYPTO', 'lang': 'en', 'trust': 9},
    {'name': 'CoinTelegraph', 'url': 'https://cointelegraph.com/rss', 'category': 'CRYPTO', 'lang': 'en', 'trust': 8},
    {'name': 'Crypto.id', 'url': 'https://crypto.id/feed/', 'category': 'CRYPTO INDONESIA', 'lang': 'id', 'trust': 7},
    {'name': 'CNBC Finance', 'url': 'https://www.cnbc.com/id/10000664/device/rss/rss.html', 'category': 'FINANCE', 'lang': 'en', 'trust': 9},
    {'name': 'Investopedia', 'url': 'https://www.investopedia.com/feedbuilder/feed/getfeed/?feedName=rss_headline', 'category': 'FINANCE', 'lang': 'en', 'trust': 8},
    {'name': 'Keuangan Bisnis.com', 'url': 'https://keuangan.bisnis.com/feed', 'category': 'KEUANGAN', 'lang': 'id', 'trust': 8},

    # =========================================================
    # TIER 5 — ESG & ENVIRONMENT
    # =========================================================
    {'name': 'ESG Today', 'url': 'https://www.esgtoday.com/feed/', 'category': 'ESG COMPLIANCE', 'lang': 'en', 'trust': 9},
    {'name': 'Reuters Climate', 'url': 'https://feeds.reuters.com/reuters/environment', 'category': 'ENVIRONMENT', 'lang': 'en', 'trust': 10},
    {'name': 'Mongabay Indonesia', 'url': 'https://www.mongabay.co.id/feed/', 'category': 'LINGKUNGAN', 'lang': 'id', 'trust': 9},

    # =========================================================
    # TIER 6 — SOCIAL, HEALTH, SCIENCE
    # =========================================================
    {'name': 'Reuters Health', 'url': 'https://feeds.reuters.com/reuters/health', 'category': 'HEALTH', 'lang': 'en', 'trust': 10},
    {'name': 'WHO News', 'url': 'https://www.who.int/rss-feeds/news-english.xml', 'category': 'HEALTHCARE', 'lang': 'en', 'trust': 10},
    {'name': 'Science Daily', 'url': 'https://www.sciencedaily.com/rss/all.xml', 'category': 'SCIENCE', 'lang': 'en', 'trust': 9},
    {'name': 'Nature.com', 'url': 'https://www.nature.com/news.rss', 'category': 'SCIENCE', 'lang': 'en', 'trust': 10},
]
