
from cryptol.quoting import *

# run_hello.py
import cryptol

# If you’re running Docker on the same machine:
cry = cryptol.connect(log_dest=open('foo.log', 'w'), reset_server=True)

# 1) Load a file from the container's working dir.
#    Because we mounted host ./cryptol-files -> /home/cryptol/files,
#    the server will see it as "files/Hello.cry".
print(to_cryptol_str_customf('double 21'))
hello = cry.load_file("files/Hello.cry")

print(f'Result of load file: {hello.result()}')
#cry.load_module('Hello')
result = cry.eval_f(f'double 21')
print("check(prop_double_shift) ->", result.result())


