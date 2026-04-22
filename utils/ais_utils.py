def get_country_from_mmsi(mmsi):
    """
    Returns (Country Name, ISO Code) based on the first 3 digits of MMSI (MID).
    """
    if not mmsi:
        return "Unknown", "unknown"
    
    mid = int(str(mmsi)[:3])
    
    # Mapping of MID to (Name, ISO-Alpha2)
    # References: https://en.wikipedia.org/wiki/Maritime_identification_digits
    MID_MAP = {
        525: ("Indonesia", "id"),
        563: ("Singapore", "sg"), 564: ("Singapore", "sg"), 565: ("Singapore", "sg"), 566: ("Singapore", "sg"),
        533: ("Malaysia", "my"),
        351: ("Panama", "pa"), 352: ("Panama", "pa"), 353: ("Panama", "pa"), 354: ("Panama", "pa"),
        355: ("Panama", "pa"), 356: ("Panama", "pa"), 357: ("Panama", "pa"), 370: ("Panama", "pa"),
        371: ("Panama", "pa"), 372: ("Panama", "pa"), 373: ("Panama", "pa"), 374: ("Panama", "pa"),
        636: ("Liberia", "lr"),
        538: ("Marshall Islands", "mh"),
        308: ("Bahamas", "bs"), 309: ("Bahamas", "bs"), 311: ("Bahamas", "bs"),
        477: ("Hong Kong", "hk"),
        412: ("China", "cn"), 413: ("China", "cn"), 414: ("China", "cn"),
        239: ("Greece", "gr"), 240: ("Greece", "gr"), 241: ("Greece", "gr"),
        209: ("Cyprus", "cy"), 210: ("Cyprus", "cy"), 212: ("Cyprus", "cy"),
        215: ("Malta", "mt"), 229: ("Malta", "mt"), 248: ("Malta", "mt"),
        232: ("United Kingdom", "gb"), 233: ("United Kingdom", "gb"), 234: ("United Kingdom", "gb"), 235: ("United Kingdom", "gb"),
        366: ("USA", "us"), 367: ("USA", "us"), 368: ("USA", "us"), 369: ("USA", "us"),
        338: ("USA", "us"),
        244: ("Netherlands", "nl"), 245: ("Netherlands", "nl"), 246: ("Netherlands", "nl"),
        226: ("France", "fr"), 227: ("France", "fr"), 228: ("France", "fr"),
        211: ("Germany", "de"), 218: ("Germany", "de"),
        247: ("Italy", "it"),
        431: ("Japan", "jp"), 432: ("Japan", "jp"),
        440: ("South Korea", "kr"), 441: ("South Korea", "kr"),
        503: ("Australia", "au"),
        512: ("New Zealand", "nz"),
        273: ("Russia", "ru"),
        601: ("South Africa", "za"),
        710: ("Brazil", "br"),
        224: ("Spain", "es"),
        263: ("Portugal", "pt")
    }
    
    if mid in MID_MAP:
        return MID_MAP[mid]
    
    # Range based generic mapping if specific MID not listed
    if 201 <= mid <= 278: return "Europe", "eu"
    if 301 <= mid <= 374: return "North/Central America", "us"
    if 401 <= mid <= 477: return "Asia", "cn"
    if 501 <= mid <= 578: return "Oceania/SE Asia", "id"
    if 601 <= mid <= 679: return "Africa", "za"
    if 701 <= mid <= 775: return "South America", "br"
    
    return "Unknown", "un"
