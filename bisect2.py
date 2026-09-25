import ast

with open('core/pdf_generator.py', encoding='utf-8') as f:
    lines = f.readlines()

for i in range(415, 538):
    temp = lines[:]
    temp[i] = "\n"
    try:
        ast.parse("".join(temp))
    except Exception as e:
        pass
    else:
        print(f"File parsed successfully when line {i} is removed!")
