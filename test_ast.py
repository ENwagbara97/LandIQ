import ast
try:
    ast.parse("f''' {{ 11pt }} '''")
    print("OK double")
except Exception as e:
    print("Double:", repr(e))

try:
    ast.parse("f''' { 11pt } '''")
    print("OK single")
except Exception as e:
    print("Single:", repr(e))
