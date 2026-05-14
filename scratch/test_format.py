
template = "http://127.0.0.1:5202/api/research/start?symbols={symbols}&analysis_type={analysis_type}"
base = "https://api.asetpedia.online"
formatted = template.format(base=base, symbols="BBCA.JK", analysis_type="full")
print(formatted)
