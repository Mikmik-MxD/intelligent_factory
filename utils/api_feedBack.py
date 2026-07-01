
def sucess_feedback(msg: str, data: dict = {}, field: str = 'data', ):
  return{
    "code": 200,
    "msg": msg,
    field: data
  }

def pendding_feedback(msg: str, data: dict = {}):
  return{
    "code": 400,
    "msg": msg,
    "data": data
  }     

def error_feedback(msg: str, data: dict = {}):
  return{
    "code": 500,
    "msg": msg,
    "data": data
  }
