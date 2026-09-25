import ast
with open('core/pdf_generator.py', encoding='utf-8') as f:
    lines = f.readlines()

s = "".join(lines[414:538]).replace('return ', '', 1)
try:
    ast.parse("x = " + s)
    print("OK")
except Exception as e:
    import traceback
    traceback.print_exc()
