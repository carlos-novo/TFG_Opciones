import re
content = open('.venv/Lib/site-packages/streamlit/static/static/js/index.Drusyo5m.js', encoding='utf-8').read()
matches = [m.start() for m in re.finditer(r'data-testid', content)]
print(f"Found {len(matches)} occurrences of data-testid.")
for m in matches[:20]:
    print(content[m-20:m+60])
