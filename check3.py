with open('core/pdf_generator.py', encoding='utf-8') as f:
    lines = f.readlines()

fstring = "".join(lines[414:537])

import re

# replace all {{ and }} with something else to not interfere
fstring = fstring.replace('{{', 'XX').replace('}}', 'YY')

depth = 0
for i, c in enumerate(fstring):
    if c == '{':
        depth += 1
    elif c == '}':
        depth -= 1
        if depth < 0:
            print("ERROR: Unmatched } at index", i)
            break
if depth > 0:
    print("ERROR: Unclosed {")

print("Depth check complete.")
