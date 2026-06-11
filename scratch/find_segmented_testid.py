import re
content = open('.venv/Lib/site-packages/streamlit/static/static/js/index.Drusyo5m.js', encoding='utf-8').read()
# Let's search for "segmented" and find any testid within 2000 chars of it.
matches = [m.start() for m in re.finditer(r'(?i)segmented_control', content)]
print(f"Found {len(matches)} occurrences of segmented_control.")
for m in matches:
    start = max(0, m - 500)
    end = min(len(content), m + 1500)
    chunk = content[start:end]
    tids = re.findall(r'data-testid="([^"]+)"', chunk)
    print("Chunk near match:")
    print("Test IDs in chunk:", tids)
    print(chunk[:400])
    print("-" * 50)
