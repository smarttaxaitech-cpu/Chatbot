import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")


# ---------------------------------
# CONNECTION
# ---------------------------------
def get_conn():
    return psycopg2.connect(
        DATABASE_URL,
        cursor_factory=RealDictCursor
    )


# ---------------------------------
# CONVERSATIONS
# ---------------------------------
def ensure_conversation(cur, conversation_id):
    cur.execute(
        """
        INSERT INTO conversations (id)
        VALUES (%s)
        ON CONFLICT (id) DO NOTHING
        """,
        (conversation_id,)
    )


# ---------------------------------
# MESSAGES
# ---------------------------------
def insert_message(
    cur,
    conversation_id,
    role,
    text,
    deductibility_type=None,
    category_tag=None,
    spending_timing=None,
    followup_question=None,
    confidence_score=None,
):
    cur.execute(
        """
        INSERT INTO messages
        (conversation_id, role, text,
         deductibility_type, category_tag,
         spending_timing, followup_question,
         confidence_score)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING id
        """,
        (
            conversation_id,
            role,
            text,
            deductibility_type,
            category_tag,
            spending_timing,
            followup_question,
            confidence_score,
        ),
    )
    return cur.fetchone()["id"]


# ---------------------------------
# FEEDBACK
# ---------------------------------
def insert_feedback(cur, conversation_id, message_id, rating, comment=None):
    cur.execute(
        """
        INSERT INTO feedback
        (conversation_id, message_id, rating, comment)
        VALUES (%s,%s,%s,%s)
        """,
        (conversation_id, message_id, rating, comment),
    )


# ---------------------------------
# EXPENSES
# ---------------------------------
def insert_expense(cur, conversation_id, category, amount, description=None):
    cur.execute(
        """
        INSERT INTO expenses
        (conversation_id, category, amount, description)
        VALUES (%s,%s,%s,%s)
        """,
        (conversation_id, category, amount, description),
    )


def get_expenses_for_conversation(cur, conversation_id):
    cur.execute(
        """
        SELECT category, amount, description
        FROM expenses
        WHERE conversation_id = %s
        ORDER BY created_at ASC
        """,
        (conversation_id,),
    )
    return cur.fetchall()


# ---------------------------------
# INCOME
# ---------------------------------
def insert_income_source(cur, conversation_id, income_type, amount, description=None):
    cur.execute(
        """
        INSERT INTO income_sources
        (conversation_id, type, amount, description)
        VALUES (%s,%s,%s,%s)
        """,
        (conversation_id, income_type, amount, description),
    )


def get_income_sources_for_conversation(cur, conversation_id):
    cur.execute(
        """
        SELECT type, amount, description
        FROM income_sources
        WHERE conversation_id = %s
        ORDER BY created_at ASC
        """,
        (conversation_id,),
    )
    return cur.fetchall()
