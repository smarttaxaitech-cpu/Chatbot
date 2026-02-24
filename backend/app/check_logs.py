from db import get_conn


def main():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("select count(*) as count from messages;")
            row = cur.fetchone()
            count = row["count"]
            print("messages count:", count)


if __name__ == "__main__":
    main()
