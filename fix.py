import re
import os

filepath = r'c:\Users\ashis\Style.ai\templates\index.html'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

content = re.sub(r'<style>.*?</style>', '<link rel="stylesheet" href="{{ url_for(\'static\', filename=\'css/style.css\') }}">', content, flags=re.DOTALL)
content = re.sub(r'<script>.*?</script>', '<script src="{{ url_for(\'static\', filename=\'js/script.js\') }}"></script>', content, flags=re.DOTALL)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)

print(f"Updates made to {filepath}")
