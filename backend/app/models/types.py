from sqlalchemy import JSON

# MySQL natively supports JSON; no dialect variant needed.
JsonType = JSON()
