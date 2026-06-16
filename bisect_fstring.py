import ast

with open('core/pdf_generator.py', encoding='utf-8') as f:
    lines = f.readlines()

for i in range(415, 538):
    subset = "".join(lines[414:i+1])
    try:
        ast.parse("s = f'''" + subset + "'''")
    except Exception as e:
        print(f"Failed at line {i}: {e}")
        break
