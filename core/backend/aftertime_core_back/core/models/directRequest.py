from django.db import connections


def __fetchall(cursor):
    "Return all rows from a cursor as a dict"
    columns = [col[0] for col in cursor.description]
    return [
        dict(zip(columns, row))
        for row in cursor.fetchall()
    ]


def direct_request(sql, parameters=None):
    cursor = connections['default'].cursor()
    if parameters is not None:
        cursor.execute(sql, parameters)
    else:
        cursor.execute(sql)

    return __fetchall(cursor)
