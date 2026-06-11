import re
content = open('.venv/Lib/site-packages/streamlit/static/static/js/index.Drusyo5m.js', encoding='utf-8').read()
matches = [m.start() for m in re.finditer(r'data-testid', content)]
print(f"Found {len(matches)} data-testid occurrences.")
for m in matches:
    chunk = content[m:m+100]
    if 'button' in chunk.lower() or 'control' in chunk.lower() or 'pills' in chunk.lower():
        print(content[m-50:m+150])
