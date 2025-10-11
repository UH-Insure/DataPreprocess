from cryptol.quoting import *
import cryptol
from saw_client.connection import *

saw = connect(url="http://localhost:8081")

path = "files/aes-mct-ecb_hpy11xa6.cry"
try:
    cry = cryptol.connect(url="http://localhost:8080", reset_server=True)
    hello = cry.load_file(path).result()
    print(hello)
except Exception as e:
    print(e)
#print(to_cryptol_str_customf('double 21'))
#hello = cry.load_file(path).result()
#print(hello)
#print(f'Result of load file: {hello.result()}')
#result = cry.eval_f(f'double 21')
#print("(prop_double_shift) ->", result.result())
#deps = cry.file_deps(path, is_file=True).result()
#print(deps)