import pymysql

# Параметры подключения к базе данных MySQL
db_params = {
        'host': 'localhost',
        'user': 'root',
        'password': 'Ose7vgt5',
        'db': 'rzd',
        'cursorclass': pymysql.cursors.DictCursor
}
def chatmigration():
    conn = pymysql.connect(**db_params)
    try:
        with conn.cursor() as cursor:
            query = f'''create table if not exists tgchatids
                        (
                            id         int auto_increment,
                            chatids varchar(255) null,
                                primary key (id)
                        );
                        '''
            cursor.execute(query)
        conn.commit()
    finally:
        conn.close()

chatmigration()