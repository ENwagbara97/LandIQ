with open('core/pdf_generator.py', encoding='utf-8') as f:
    lines = f.readlines()

fstring = "".join(lines[414:537])

# Let's count {{ and }} and single { and }
import re
print("Single {: ", len(re.findall(r'(?<!\{)\{(?!\{)', fstring)))
print("Single }: ", len(re.findall(r'(?<!\})\}(?!\})', fstring)))
print("Double {{: ", len(re.findall(r'\{\{', fstring)))
print("Double }}: ", len(re.findall(r'\}\}', fstring)))

# Print all single { with their lines
for i, line in enumerate(lines[414:537]):
    # find { not preceded or followed by {
    matches = re.finditer(r'(?<!\{)\{(?!\{)', line)
    for m in matches:
        print(f"Line {415+i}: {line.strip()}")
